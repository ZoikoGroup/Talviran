"""The only code path allowed to write market.accepted_fact (DATA-002
doctrine) — reconcile_and_publish() either publishes a new fact version,
records NO_CHANGE, or flags a CONFLICT. It never silently picks a winner
outside what the ReconciliationPolicy explicitly authorizes, and it never
mutates an existing accepted_fact row — a superseded fact is closed
(knowledge_range upper bound set, status flipped) and a new row is
inserted, so history is never rewritten in place.
"""

import datetime as dt
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.models import (
    AcceptedFact,
    FactObservationLink,
    OutboxEvent,
    ReconciliationDecision,
)
from app.modules.market.pipeline.reconciliation_policy import (
    CONFLICT_ACTION_PREFER_ORDER,
    ReconciliationPolicy,
)

DECISION_ACCEPTED = "ACCEPTED"
DECISION_CONFLICT = "CONFLICT"
DECISION_NO_CHANGE = "NO_CHANGE"


@dataclass(frozen=True)
class CandidateObservation:
    observation_id: uuid.UUID
    source_code: str
    value: dict[str, Any]


@dataclass(frozen=True)
class ReconciliationOutcome:
    decision: str
    accepted_fact_id: uuid.UUID | None
    reason: str


def _value_key(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, default=str)


async def _get_current_accepted_fact(
    session: AsyncSession, subject_id: uuid.UUID, metric_id: str
) -> AcceptedFact | None:
    return (
        await session.execute(
            select(AcceptedFact).where(
                AcceptedFact.subject_id == subject_id,
                AcceptedFact.metric_id == metric_id,
                AcceptedFact.status == "ACTIVE",
            )
        )
    ).scalar_one_or_none()


async def reconcile_and_publish(
    session: AsyncSession,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    metric_id: str,
    candidates: list[CandidateObservation],
    policy: ReconciliationPolicy,
    valid_range: Range[dt.datetime],
    knowledge_time: dt.datetime,
) -> ReconciliationOutcome:
    """`valid_range` describes when the fact is true IN THE WORLD (e.g. from
    an instrument's first_issue_date) — the caller supplies it, since only
    the caller knows the metric's real-world validity semantics.
    `knowledge_time` is the separate axis: when WE came to believe it.
    A correction (as opposed to a genuine real-world change) keeps the same
    valid_range across versions and only closes/reopens knowledge_range —
    that's the whole point of the two axes being independent, and why the
    exclusion constraint requires BOTH to overlap before rejecting: two
    versions may legitimately share a valid_range as long as their
    knowledge_range don't overlap.
    """
    if not candidates:
        raise ValueError("reconcile_and_publish requires at least one candidate")

    grouped: dict[str, list[CandidateObservation]] = {}
    for candidate in candidates:
        grouped.setdefault(_value_key(candidate.value), []).append(candidate)

    if len(grouped) > 1 and policy.conflict_action != CONFLICT_ACTION_PREFER_ORDER:
        reason = f"{len(grouped)} disagreeing values across sources: {sorted(grouped.keys())}"
        decision = ReconciliationDecision(
            subject_id=subject_id, metric_id=metric_id, decision=DECISION_CONFLICT, reason=reason
        )
        session.add(decision)
        return ReconciliationOutcome(
            decision=DECISION_CONFLICT, accepted_fact_id=None, reason=reason
        )

    if len(grouped) > 1:
        # PREFER_ORDER: resolved by precedence, but still logged as a
        # conflict decision — never a silent, unexplained pick.
        winning_source = next(
            code
            for code in policy.ordered_source_codes
            if any(c.source_code == code for c in candidates)
        )
        chosen_group = next(
            group
            for group in grouped.values()
            if any(c.source_code == winning_source for c in group)
        )
        candidate_value = chosen_group[0].value
        observation_ids = [c.observation_id for c in chosen_group]
        conflict_reason: str | None = (
            f"{len(grouped)} disagreeing values; "
            f"resolved by precedence to source {winning_source!r}"
        )
    else:
        only_group = next(iter(grouped.values()))
        candidate_value = only_group[0].value
        observation_ids = [c.observation_id for c in only_group]
        conflict_reason = None

    current = await _get_current_accepted_fact(session, subject_id, metric_id)

    if current is not None and _value_key(current.value) == _value_key(candidate_value):
        reason = "candidate matches current accepted fact"
        decision = ReconciliationDecision(
            subject_id=subject_id,
            metric_id=metric_id,
            decision=DECISION_NO_CHANGE,
            reason=reason,
            accepted_fact_id=current.id,
        )
        session.add(decision)
        return ReconciliationOutcome(
            decision=DECISION_NO_CHANGE, accepted_fact_id=current.id, reason=reason
        )

    if current is not None:
        # Close the old row FIRST and flush it before the new row is
        # inserted — the exclusion constraint is checked at INSERT time
        # against the DB's current state, so inserting the new row first
        # would have Postgres compare against the old row's still-open
        # knowledge_range and reject a pair that's actually fine.
        assert current.knowledge_range.lower is not None  # our own rows always set this
        current.knowledge_range = Range(
            lower=current.knowledge_range.lower, upper=knowledge_time, bounds="[)"
        )
        current.status = "SUPERSEDED"
        await session.flush()

    new_fact = AcceptedFact(
        subject_type=subject_type,
        subject_id=subject_id,
        metric_id=metric_id,
        valid_range=valid_range,
        knowledge_range=Range(lower=knowledge_time, upper=None, bounds="[)"),
        value=candidate_value,
        status="ACTIVE",
    )
    session.add(new_fact)
    await session.flush()

    if current is not None:
        current.superseded_by_id = new_fact.id

    for observation_id in observation_ids:
        session.add(
            FactObservationLink(
                accepted_fact_id=new_fact.id,
                source_observation_id=observation_id,
                role="PRIMARY",
            )
        )

    reason = conflict_reason or (
        "first accepted fact for this subject/metric"
        if current is None
        else "value changed, new version published"
    )
    decision = ReconciliationDecision(
        subject_id=subject_id,
        metric_id=metric_id,
        decision=DECISION_ACCEPTED,
        reason=reason,
        accepted_fact_id=new_fact.id,
    )
    session.add(decision)

    session.add(
        OutboxEvent(
            event_type="accepted_fact.published",
            payload={
                "accepted_fact_id": str(new_fact.id),
                "subject_id": str(subject_id),
                "metric_id": metric_id,
            },
        )
    )

    return ReconciliationOutcome(
        decision=DECISION_ACCEPTED, accepted_fact_id=new_fact.id, reason=reason
    )
