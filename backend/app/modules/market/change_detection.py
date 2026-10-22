"""Before/after change detection over versioned accepted_fact history
(PRD roadmap item #3, "what changed in the market") — the diff engine
itself. Materiality classification (materiality.py) is deliberately pure
and DB-independent; this module is the thin, also-deterministic layer that
finds which two real AcceptedFact rows to compare in the first place, and
hands their real evidence IDs back so a caller can build a real
EvidenceBundle from them — never a generated or LLM-composed pair.

Two genuinely different "before" shapes exist, both real and both
detected here:
1. A correction - reconcile.py never rewrites a row in place; it closes
   the superseded row's knowledge_range, flips its status, and inserts a
   new ACTIVE row linked back via superseded_by_id. Tried first: it's
   unambiguous when it exists (see reconcile.py's own docstring).
2. A genuine time-series step (e.g. yesterday's yield-curve point vs
   today's) - many ACTIVE rows coexist for the same subject_id/metric_id,
   one per real-world period, never superseding each other. Falls back to
   comparing the two most recent by valid_range when no correction exists.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.materiality import DEFAULT_MATERIALITY_RULES, classify_materiality
from app.modules.market.models import AcceptedFact
from app.modules.market.queries import latest_accepted_fact


@dataclass(frozen=True)
class DetectedChange:
    subject_id: uuid.UUID
    metric_id: str
    old_fact_id: uuid.UUID
    new_fact_id: uuid.UUID
    old_value: dict[str, object]
    new_value: dict[str, object]
    is_material: bool
    explanation: str


@dataclass(frozen=True)
class NoChangeDetected:
    reason: str


async def _predecessor_via_correction(
    session: AsyncSession, *, current: AcceptedFact
) -> AcceptedFact | None:
    return (
        await session.execute(
            select(AcceptedFact).where(AcceptedFact.superseded_by_id == current.id)
        )
    ).scalar_one_or_none()


async def _two_most_recent_active_facts(
    session: AsyncSession, *, subject_id: uuid.UUID, metric_id: str
) -> list[AcceptedFact]:
    return list(
        (
            await session.execute(
                select(AcceptedFact)
                .where(
                    AcceptedFact.subject_id == subject_id,
                    AcceptedFact.metric_id == metric_id,
                    AcceptedFact.status == "ACTIVE",
                )
                .order_by(func.lower(AcceptedFact.valid_range).desc())
                .limit(2)
            )
        )
        .scalars()
        .all()
    )


async def detect_change(
    session: AsyncSession, *, subject_id: uuid.UUID, metric_id: str
) -> DetectedChange | NoChangeDetected:
    current = await latest_accepted_fact(session, subject_id=subject_id, metric_id=metric_id)
    if current is None:
        return NoChangeDetected(reason="no accepted fact exists yet for this subject/metric")

    predecessor = await _predecessor_via_correction(session, current=current)
    if predecessor is None:
        two_most_recent = await _two_most_recent_active_facts(
            session, subject_id=subject_id, metric_id=metric_id
        )
        if len(two_most_recent) < 2:
            return NoChangeDetected(
                reason="only one recorded value exists; nothing to compare it against"
            )
        current, predecessor = two_most_recent[0], two_most_recent[1]

    rule = DEFAULT_MATERIALITY_RULES.get(metric_id)
    is_material, explanation = classify_materiality(predecessor.value, current.value, rule)

    return DetectedChange(
        subject_id=subject_id,
        metric_id=metric_id,
        old_fact_id=predecessor.id,
        new_fact_id=current.id,
        old_value=predecessor.value,
        new_value=current.value,
        is_material=is_material,
        explanation=explanation,
    )
