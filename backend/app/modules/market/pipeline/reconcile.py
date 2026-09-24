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
from decimal import Decimal, InvalidOperation
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


def _values_agree(a: dict[str, Any], b: dict[str, Any], policy: ReconciliationPolicy) -> bool:
    """Exact match on every field when policy.tolerance is None (every
    metric's behavior before this existed, and every metric that still has
    no tolerance configured, e.g. reference terms). When both tolerance and
    tolerance_field are set, only that one field gets numeric near-match -
    every other field still requires an exact match. Found via a real gap:
    FX_SPOT_RATE_POLICY declared a tolerance that reconcile_and_publish
    never actually consulted, so two genuine sources for the same real
    rate (which will almost never produce byte-identical decimal strings)
    would have flagged CONFLICT every single day.
    """
    if policy.tolerance is None or policy.tolerance_field is None:
        return _value_key(a) == _value_key(b)

    field = policy.tolerance_field
    a_rest = {k: v for k, v in a.items() if k != field}
    b_rest = {k: v for k, v in b.items() if k != field}
    if _value_key(a_rest) != _value_key(b_rest):
        return False
    try:
        a_num = Decimal(str(a[field]))
        b_num = Decimal(str(b[field]))
    except (KeyError, InvalidOperation):
        return False
    return abs(a_num - b_num) <= policy.tolerance


def _representative_value(
    group: list[CandidateObservation], policy: ReconciliationPolicy
) -> dict[str, Any]:
    """Which candidate's exact value becomes the published fact when a
    group agrees (exactly, or within tolerance) - policy.ordered_source_
    codes precedence decides, same rule CONFLICT_ACTION_PREFER_ORDER
    already uses to resolve a genuine disagreement. Falls back to the
    first candidate only if none of the group's sources appear in the
    policy's precedence list at all (shouldn't happen for a well-formed
    policy, but never crash over it).
    """
    for code in policy.ordered_source_codes:
        match = next((c for c in group if c.source_code == code), None)
        if match is not None:
            return match.value
    return group[0].value


async def _get_current_accepted_fact(
    session: AsyncSession,
    subject_id: uuid.UUID,
    metric_id: str,
    valid_range: Range[dt.datetime],
) -> AcceptedFact | None:
    """Scoped to the fact whose valid_range actually overlaps the candidate's
    — not just "any ACTIVE fact for this subject/metric". For a metric with
    one open-ended, occasionally-corrected value (e.g. gilt reference terms)
    there's only ever one such row. But for a genuine time series (e.g. a
    yield curve point, where each day's rate is permanently true for its own
    day and never "corrects" another day's), multiple ACTIVE rows coexist
    for the same subject/metric — the accepted_fact_no_overlap exclusion
    constraint already guarantees at most one of them overlaps any given
    valid_range, so scalar_one_or_none() is safe here.
    """
    return (
        await session.execute(
            select(AcceptedFact).where(
                AcceptedFact.subject_id == subject_id,
                AcceptedFact.metric_id == metric_id,
                AcceptedFact.status == "ACTIVE",
                AcceptedFact.valid_range.op("&&")(valid_range),
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

    # A list of clusters, not a dict keyed by exact value, so that a
    # tolerance-configured policy can group "near enough" values together
    # (see _values_agree) rather than only byte-identical ones. With no
    # tolerance configured this produces exactly the same clusters the old
    # dict-based grouping did, just via pairwise comparison instead of a
    # hash key — candidate counts are always tiny (one per source), so the
    # O(n^2) comparison is irrelevant in practice.
    groups: list[list[CandidateObservation]] = []
    for candidate in candidates:
        matched_group = next(
            (g for g in groups if _values_agree(g[0].value, candidate.value, policy)), None
        )
        if matched_group is not None:
            matched_group.append(candidate)
        else:
            groups.append([candidate])

    if len(groups) > 1 and policy.conflict_action != CONFLICT_ACTION_PREFER_ORDER:
        values = sorted(_value_key(g[0].value) for g in groups)
        reason = f"{len(groups)} disagreeing values across sources: {values}"
        decision = ReconciliationDecision(
            subject_id=subject_id, metric_id=metric_id, decision=DECISION_CONFLICT, reason=reason
        )
        session.add(decision)
        return ReconciliationOutcome(
            decision=DECISION_CONFLICT, accepted_fact_id=None, reason=reason
        )

    if len(groups) > 1:
        # PREFER_ORDER: resolved by precedence, but still logged as a
        # conflict decision — never a silent, unexplained pick.
        winning_source = next(
            code
            for code in policy.ordered_source_codes
            if any(c.source_code == code for c in candidates)
        )
        chosen_group = next(
            group for group in groups if any(c.source_code == winning_source for c in group)
        )
        candidate_value = _representative_value(chosen_group, policy)
        observation_ids = [c.observation_id for c in chosen_group]
        conflict_reason: str | None = (
            f"{len(groups)} disagreeing values; "
            f"resolved by precedence to source {winning_source!r}"
        )
    else:
        only_group = groups[0]
        # Now that a group can genuinely hold more than one agreeing
        # candidate (tolerance made real multi-source agreement reachable
        # for the first time - see ingest_tail._gather_candidates), which
        # one's exact value becomes canonical must be policy-driven, not
        # whatever order the DB happened to return - same precedence rule
        # the PREFER_ORDER conflict branch above already uses.
        candidate_value = _representative_value(only_group, policy)
        observation_ids = [c.observation_id for c in only_group]
        conflict_reason = None

    current = await _get_current_accepted_fact(session, subject_id, metric_id, valid_range)

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
