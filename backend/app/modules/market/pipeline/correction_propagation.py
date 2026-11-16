"""UAT gap-analysis G12: "Corrections create a new version and a
material-change link; affected saved research and monitors are marked
for reassessment." reconcile.py already does the first half - a
correction has always created a new accepted_fact row and linked the old
one to it via superseded_by_id. This module is the second half: record
the correction as a durable, queryable event, and - only when the value
change is material - find every saved research message and delivered
alert whose evidence bundle cited the now-superseded fact, and flag each
one.

Called once, synchronously, from reconcile.py's own correction branch,
in the same transaction as the correction itself - a correction is never
"complete" without this running, same discipline as the outbox event
reconcile.py already writes alongside every accepted_fact.

This module only READS across evidence/research/monitoring (which
accepted_fact ingestion already does throughout the pipeline, e.g.
pipeline/identity_resolution.py reads reference.instrument_alias) - it
never writes those modules' own tables directly. The two actual writes
go through each owning module's own service function
(research.service.mark_messages_for_reassessment,
monitoring.alerts.mark_alerts_for_reassessment), matching this
codebase's no-cross-module-direct-writes discipline.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uuid7 import new_uuid7
from app.modules.evidence.models import EvidenceBundle, EvidenceMember
from app.modules.market.materiality import DEFAULT_MATERIALITY_RULES, classify_materiality
from app.modules.market.models import AcceptedFact, CorrectionEvent

# Deferred to call time, not module level: monitoring.alerts transitively
# imports rule_engine -> calculation.pipeline.curve_pricing ->
# market.pipeline.curve_ingest -> ingest_tail -> reconcile, which itself
# imports this module - a real circular import, not an ordering accident
# to paper over. reconcile.py (this module's only caller) is always fully
# loaded by the time record_correction_and_propagate actually runs, so
# the import is safe here even though it can't be at the top of the file.


async def _affected_evidence_bundles(
    session: AsyncSession, *, old_fact_id: uuid.UUID
) -> list[EvidenceBundle]:
    """Every evidence bundle that cited `old_fact_id` as a FACT member -
    the universe of saved answers/alerts a correction to that fact could
    possibly have touched. A bundle with no research_message_id and no
    alert referencing it is simply not propagated anywhere (e.g. one built
    for a since-deleted conversation, or a monitoring alert's bundle that
    was superseded before delivery) - not an error.
    """
    bundle_ids = (
        await session.execute(
            select(EvidenceMember.evidence_bundle_id).where(
                EvidenceMember.kind == "FACT",
                EvidenceMember.accepted_fact_id == old_fact_id,
            )
        )
    ).scalars().all()
    if not bundle_ids:
        return []
    return list(
        (
            await session.execute(
                select(EvidenceBundle).where(EvidenceBundle.id.in_(set(bundle_ids)))
            )
        )
        .scalars()
        .all()
    )


async def record_correction_and_propagate(
    session: AsyncSession, *, old_fact: AcceptedFact, new_fact: AcceptedFact
) -> CorrectionEvent:
    """Called from reconcile.py immediately after `old_fact.superseded_by_id
    = new_fact.id` is set, only on the genuine-value-change path (never for
    an agreeing-source republish of the same value - see reconcile.py's own
    call site for that gate). Always records the event; only propagates
    the reassessment flag when classify_materiality says the change is
    material, so an immaterial correction (e.g. a sub-threshold yield
    wobble) doesn't flag every saved answer that ever cited the metric.
    """
    from app.modules.monitoring.alerts import mark_alerts_for_reassessment
    from app.modules.research.service import mark_messages_for_reassessment

    rule = DEFAULT_MATERIALITY_RULES.get(new_fact.metric_id)
    is_material, explanation = classify_materiality(old_fact.value, new_fact.value, rule)

    event = CorrectionEvent(
        id=new_uuid7(),
        subject_type=new_fact.subject_type,
        subject_id=new_fact.subject_id,
        metric_id=new_fact.metric_id,
        old_fact_id=old_fact.id,
        new_fact_id=new_fact.id,
        is_material=is_material,
        explanation=explanation,
    )
    session.add(event)
    await session.flush()

    if not is_material:
        return event

    bundles = await _affected_evidence_bundles(session, old_fact_id=old_fact.id)
    if not bundles:
        return event

    message_ids = [b.research_message_id for b in bundles if b.research_message_id is not None]
    bundle_ids = [b.id for b in bundles]

    await mark_messages_for_reassessment(
        session, message_ids=message_ids, correction_event_id=event.id
    )
    await mark_alerts_for_reassessment(
        session, evidence_bundle_ids=bundle_ids, correction_event_id=event.id
    )

    return event
