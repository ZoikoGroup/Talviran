"""UAT gap-analysis G12: "Corrections create a new version and a
material-change link; affected saved research and monitors are marked
for reassessment." Proves the full chain: a material value-change
correction to an accepted_fact records a market.correction_event and
flags every saved research.message and monitoring.alert whose evidence
bundle cited the now-superseded fact - and proves the negative cases
(immaterial change, no affected rows) don't over-flag.
"""

import datetime as dt
import uuid
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import EvidenceBundle, EvidenceMember
from app.modules.identity import service as identity_service
from app.modules.market.models import AcceptedFact, CorrectionEvent
from app.modules.market.pipeline.correction_propagation import record_correction_and_propagate
from app.modules.monitoring.models import (
    PREDICATE_CROSSES_ABOVE,
    STATUS_ALERT_CREATED,
    STATUS_ARMED,
    SUBJECT_TYPE_INSTRUMENT,
    Alert,
    MonitoringRule,
    MonitoringRuleVersion,
    RuleEvaluation,
)
from app.modules.research import service as research_service
from app.modules.research.crypto import DEK_BYTES, LocalKeyWrapper

_METRIC_WITH_RULE = "UK_GILT_NOMINAL_SPOT_CURVE"  # 5bp threshold, DEFAULT_MATERIALITY_RULES

#: Fixed so tests don't depend on environment configuration (same pattern
#: test_research_isolation.py uses).
_WRAPPER = LocalKeyWrapper(b"\x22" * DEK_BYTES, key_name="test/local-correction-propagation")

_VALID_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime(2026, 9, 10, tzinfo=dt.UTC),
    upper=dt.datetime(2026, 9, 11, tzinfo=dt.UTC),
    bounds="[)",
)


def _email() -> str:
    return f"correction-prop-{uuid.uuid4().hex[:12]}@example.com"


async def _register(
    session: AsyncSession, http: httpx.AsyncClient
) -> tuple[uuid.UUID, uuid.UUID]:
    login = await identity_service.register(
        session, email=_email(), password="correct-horse-9", http=http
    )
    await session.commit()
    await identity_service.apply_rls_context(
        session, account_id=login.identity.account_id, principal_id=login.identity.principal_id
    )
    return login.identity.account_id, login.identity.principal_id


async def _seed_fact_pair(
    session: AsyncSession, *, subject_id: uuid.UUID, metric_id: str, old_value: str, new_value: str
) -> tuple[AcceptedFact, AcceptedFact]:
    old_fact = AcceptedFact(
        subject_type="TEST_SUBJECT", subject_id=subject_id, metric_id=metric_id,
        valid_range=_VALID_RANGE,
        knowledge_range=Range(
            lower=dt.datetime(2026, 9, 10, 16, 0, tzinfo=dt.UTC),
            upper=dt.datetime(2026, 9, 15, 9, 0, tzinfo=dt.UTC), bounds="[)",
        ),
        value={"spot_rate_pct": old_value}, status="SUPERSEDED",
    )
    session.add(old_fact)
    await session.flush()
    new_fact = AcceptedFact(
        subject_type="TEST_SUBJECT", subject_id=subject_id, metric_id=metric_id,
        valid_range=_VALID_RANGE,
        knowledge_range=Range(
            lower=dt.datetime(2026, 9, 15, 9, 0, tzinfo=dt.UTC), upper=None, bounds="[)"
        ),
        value={"spot_rate_pct": new_value}, status="ACTIVE",
    )
    session.add(new_fact)
    await session.flush()
    old_fact.superseded_by_id = new_fact.id
    return old_fact, new_fact


async def test_material_correction_records_event_and_marks_nothing_with_no_bundles(
    db_session: AsyncSession,
) -> None:
    """Baseline: a correction with no evidence bundle referencing the old
    fact at all must still record the correction_event (full history), but
    propagate nothing - there is nothing to flag."""
    subject_id = uuid.uuid4()
    old_fact, new_fact = await _seed_fact_pair(
        db_session, subject_id=subject_id, metric_id=_METRIC_WITH_RULE,
        old_value="5.000000", new_value="5.400000",  # 40bp move, well over the 5bp threshold
    )

    event = await record_correction_and_propagate(db_session, old_fact=old_fact, new_fact=new_fact)
    await db_session.flush()

    assert event.is_material is True
    assert event.old_fact_id == old_fact.id
    assert event.new_fact_id == new_fact.id

    persisted = await db_session.get(CorrectionEvent, event.id)
    assert persisted is not None


async def test_immaterial_correction_records_event_but_is_material_false(
    db_session: AsyncSession,
) -> None:
    """A sub-threshold move (2bp, under the 5bp rule) is still a real
    correction - it gets its own event - but must not be flagged material."""
    subject_id = uuid.uuid4()
    old_fact, new_fact = await _seed_fact_pair(
        db_session, subject_id=subject_id, metric_id=_METRIC_WITH_RULE,
        old_value="5.000000", new_value="5.020000",
    )

    event = await record_correction_and_propagate(db_session, old_fact=old_fact, new_fact=new_fact)

    assert event.is_material is False


async def test_material_correction_flags_the_saved_message_that_cited_it(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient
) -> None:
    account_id, principal_id = await _register(db_session, supabase_http)
    dek = await research_service.account_dek(
        db_session, account_id=account_id, wrapper=_WRAPPER
    )
    conversation = await research_service.create_conversation(
        db_session, account_id=account_id, principal_id=principal_id, model="talvrin-go", dek=dek
    )
    message = await research_service.append_message(
        db_session,
        account_id=account_id,
        conversation_id=conversation.id,
        role=research_service.ROLE_ASSISTANT,
        content="The 10-year gilt yield is 5.00%.",
        dek=dek,
    )
    await db_session.commit()
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    subject_id = uuid.uuid4()
    old_fact, new_fact = await _seed_fact_pair(
        db_session, subject_id=subject_id, metric_id=_METRIC_WITH_RULE,
        old_value="5.000000", new_value="5.400000",
    )
    bundle = EvidenceBundle(
        purpose_type="RESEARCH_ANSWER", knowledge_time=dt.datetime.now(dt.UTC),
        status="READY", research_message_id=message.id,
    )
    db_session.add(bundle)
    await db_session.flush()
    db_session.add(
        EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=old_fact.id)
    )
    await db_session.flush()

    event = await record_correction_and_propagate(db_session, old_fact=old_fact, new_fact=new_fact)
    await db_session.commit()
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    messages = await research_service.list_messages(
        db_session, conversation_id=conversation.id, dek=dek
    )
    flagged = next(m for m in messages if m.id == message.id)
    assert flagged.reassessment_correction_id == event.id


async def test_immaterial_correction_does_not_flag_the_saved_message(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient
) -> None:
    account_id, principal_id = await _register(db_session, supabase_http)
    dek = await research_service.account_dek(
        db_session, account_id=account_id, wrapper=_WRAPPER
    )
    conversation = await research_service.create_conversation(
        db_session, account_id=account_id, principal_id=principal_id, model="talvrin-go", dek=dek
    )
    message = await research_service.append_message(
        db_session,
        account_id=account_id,
        conversation_id=conversation.id,
        role=research_service.ROLE_ASSISTANT,
        content="The 10-year gilt yield is 5.00%.",
        dek=dek,
    )
    await db_session.commit()
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    subject_id = uuid.uuid4()
    old_fact, new_fact = await _seed_fact_pair(
        db_session, subject_id=subject_id, metric_id=_METRIC_WITH_RULE,
        old_value="5.000000", new_value="5.020000",  # 2bp - under the 5bp threshold
    )
    bundle = EvidenceBundle(
        purpose_type="RESEARCH_ANSWER", knowledge_time=dt.datetime.now(dt.UTC),
        status="READY", research_message_id=message.id,
    )
    db_session.add(bundle)
    await db_session.flush()
    db_session.add(
        EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=old_fact.id)
    )
    await db_session.flush()

    await record_correction_and_propagate(db_session, old_fact=old_fact, new_fact=new_fact)
    await db_session.commit()
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    messages = await research_service.list_messages(
        db_session, conversation_id=conversation.id, dek=dek
    )
    flagged = next(m for m in messages if m.id == message.id)
    assert flagged.reassessment_correction_id is None


async def test_material_correction_flags_an_alert_that_cited_it(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient
) -> None:
    account_id, principal_id = await _register(db_session, supabase_http)

    rule = MonitoringRule(account_id=account_id)
    db_session.add(rule)
    await db_session.flush()
    rule_version = MonitoringRuleVersion(
        account_id=account_id, rule_id=rule.id, version=1, status=STATUS_ARMED,
        subject_type=SUBJECT_TYPE_INSTRUMENT, subject_id=uuid.uuid4(),
        metric_id=_METRIC_WITH_RULE, predicate=PREDICATE_CROSSES_ABOVE,
        threshold_value=Decimal("5.0"), effective_from=dt.datetime.now(dt.UTC),
        created_by_principal_id=principal_id,
    )
    db_session.add(rule_version)
    await db_session.flush()

    subject_id = uuid.uuid4()
    old_fact, new_fact = await _seed_fact_pair(
        db_session, subject_id=subject_id, metric_id=_METRIC_WITH_RULE,
        old_value="5.000000", new_value="5.400000",
    )
    bundle = EvidenceBundle(
        purpose_type="MONITORING_ALERT", knowledge_time=dt.datetime.now(dt.UTC), status="READY",
    )
    db_session.add(bundle)
    await db_session.flush()
    db_session.add(
        EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=old_fact.id)
    )
    evaluation = RuleEvaluation(
        account_id=account_id, rule_version_id=rule_version.id,
        evaluation_key=f"test-{uuid.uuid4().hex}", outcome="MATCH",
        trigger_type="SCHEDULED_SWEEP", knowledge_time=dt.datetime.now(dt.UTC),
        evaluator_version="crossing_v1",
    )
    db_session.add(evaluation)
    await db_session.flush()
    alert = Alert(
        account_id=account_id, rule_id=rule.id, rule_version_id=rule_version.id,
        evaluation_id=evaluation.id, alert_type="CROSSING", subject_id=subject_id,
        metric_id=_METRIC_WITH_RULE, observed_value=Decimal("5.000000"),
        threshold_value=Decimal("5.0"), knowledge_time=dt.datetime.now(dt.UTC),
        evidence_bundle_id=bundle.id, status=STATUS_ALERT_CREATED,
    )
    db_session.add(alert)
    await db_session.flush()
    await db_session.commit()
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    event = await record_correction_and_propagate(db_session, old_fact=old_fact, new_fact=new_fact)
    await db_session.commit()
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=principal_id
    )

    refreshed = (
        await db_session.execute(select(Alert).where(Alert.id == alert.id))
    ).scalar_one()
    assert refreshed.reassessment_correction_id == event.id
