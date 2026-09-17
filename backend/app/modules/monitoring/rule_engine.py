"""First slice of PLT-MON-001's evaluation engine (§7): only the two
simplest predicates, CROSSES_ABOVE/CROSSES_BELOW, and only against a
single scalar value already sitting in an accepted_fact's JSONB `value`.

Deliberately NOT implemented yet (later slices, once there's a reason to
build them for real rather than guess at the shape):
  - CHANGES_BY / ENTERS_STATE / DOCUMENT_PUBLISHED / EVENT_SCHEDULED
  - hysteresis and debounce (§8) - every raw crossing here is treated as
    real; MON-001 gives no concrete tolerance values to encode anyway
  - SUPPRESSED / BLOCKED_POLICY / BLOCKED_RIGHTS / INPUT_STALE /
    INPUT_UNAVAILABLE outcomes - no PDP/rights gate or freshness check is
    wired into evaluation yet (see evidence/service.py and
    market/freshness.py for those, elsewhere)
  - automatic triggering from ingestion - this is a callable a caller
    invokes explicitly (mirrors compute_and_persist_model_implied_price's
    own P1 scope before the P2 job queue existed)

SCALAR_VALUE_KEYS is this module's own registration: PLT-MON-001 doesn't
define how to pull "the one number being watched" out of a metric's JSONB
value shape (each metric's shape is defined by its own producer, e.g.
curve_ingest.py, curve_pricing.py).

Only market.accepted_fact-backed metrics are supported this slice - e.g.
one gilt-curve tenor's spot rate (subject_id is that tenor's synthetic
curve-point id, per curve_ingest.curve_point_subject_id). A model-implied
price (METRIC_MODEL_IMPLIED_CLEAN_PRICE) lives in calculation.
calculation_result, a different table entirely - watching it needs
RuleEvaluationInput to support a calculation_result reference too (a
discriminated union, mirroring evidence.models.EvidenceMember's existing
pattern for the same "could be one of several truth-bearing tables"
problem), which is a real, separate follow-up, not a same-day addition.
Reference terms (GILT_REFERENCE_TERMS) is a multi-field record, not a
scalar, and is never registrable here regardless.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import METRIC_UK_GILT_NOMINAL_SPOT_CURVE
from app.modules.market.queries import latest_accepted_fact
from app.modules.monitoring.models import (
    OUTCOME_INITIAL_STATE,
    OUTCOME_MATCH,
    OUTCOME_NO_MATCH,
    OUTCOME_STILL_MATCHED,
    PREDICATE_CROSSES_ABOVE,
    PREDICATE_CROSSES_BELOW,
    STATUS_ARMED,
    MonitoringRuleVersion,
    RuleEvaluation,
    RuleEvaluationInput,
)

EVALUATOR_VERSION = "crossing_v1"

SCALAR_VALUE_KEYS: dict[str, str] = {
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE: "spot_rate_pct",
}

CURRENT_VALUE_ROLE = "CURRENT_VALUE"


@dataclass(frozen=True)
class RuleEvaluationSkipped:
    reason: str


@dataclass(frozen=True)
class RuleEvaluationRecorded:
    rule_evaluation_id: uuid.UUID
    outcome: str


def _evaluation_key(
    *,
    rule_version_id: uuid.UUID,
    trigger_type: str,
    trigger_id: uuid.UUID | None,
    knowledge_time: dt.datetime,
) -> str:
    """hash(rule_version_id, trigger_type, trigger_fact_or_event_id,
    knowledge_time, evaluator_version) per MON-001 §7.1 - the same
    (rule version, trigger, knowledge time, evaluator version) combination
    must never produce a second row.
    """
    raw = (
        f"{rule_version_id}:{trigger_type}:{trigger_id}:"
        f"{knowledge_time.isoformat()}:{EVALUATOR_VERSION}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()


async def _previous_evaluation(
    session: AsyncSession, *, rule_version_id: uuid.UUID
) -> RuleEvaluation | None:
    return (
        await session.execute(
            select(RuleEvaluation)
            .where(RuleEvaluation.rule_version_id == rule_version_id)
            .order_by(RuleEvaluation.evaluated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _resolve_current_value_input(
    session: AsyncSession, *, rule_evaluation_id: uuid.UUID
) -> Decimal | None:
    """Re-resolves the observed value a prior evaluation was based on, by
    following its recorded evidence link - never re-derived or cached
    redundantly on RuleEvaluation itself (calculation_input's own
    traceability pattern).
    """
    accepted_fact_id = (
        await session.execute(
            select(RuleEvaluationInput.accepted_fact_id).where(
                RuleEvaluationInput.rule_evaluation_id == rule_evaluation_id,
                RuleEvaluationInput.role == CURRENT_VALUE_ROLE,
            )
        )
    ).scalar_one_or_none()
    if accepted_fact_id is None:
        return None

    fact = await session.get(AcceptedFact, accepted_fact_id)
    if fact is None:
        return None
    value_key = SCALAR_VALUE_KEYS.get(fact.metric_id)
    if value_key is None:
        return None
    return Decimal(str(fact.value[value_key]))


async def evaluate_rule_version(
    session: AsyncSession,
    *,
    rule_version_id: uuid.UUID,
    trigger_type: str,
    trigger_id: uuid.UUID | None,
) -> RuleEvaluationRecorded | RuleEvaluationSkipped:
    rule_version = await session.get(MonitoringRuleVersion, rule_version_id)
    if rule_version is None:
        return RuleEvaluationSkipped(reason=f"no monitoring_rule_version {rule_version_id}")

    # A DRAFT/PAUSED/RETIRED rule must never actually evaluate for real -
    # same fail-closed discipline as curve_pricing.py's DRAFT-spec gate.
    if rule_version.status != STATUS_ARMED:
        return RuleEvaluationSkipped(
            reason=f"rule_version {rule_version_id} is not ARMED (status={rule_version.status})"
        )

    if rule_version.predicate not in (PREDICATE_CROSSES_ABOVE, PREDICATE_CROSSES_BELOW):
        return RuleEvaluationSkipped(
            reason=f"predicate {rule_version.predicate!r} is not yet implemented"
        )

    value_key = SCALAR_VALUE_KEYS.get(rule_version.metric_id)
    if value_key is None:
        return RuleEvaluationSkipped(
            reason=f"no scalar value extractor registered for metric_id={rule_version.metric_id!r}"
        )

    current_fact = await latest_accepted_fact(
        session, subject_id=rule_version.subject_id, metric_id=rule_version.metric_id
    )
    if current_fact is None:
        return RuleEvaluationSkipped(
            reason=(
                f"no accepted_fact at all yet for subject_id={rule_version.subject_id} "
                f"metric_id={rule_version.metric_id!r}"
            )
        )

    current_value = Decimal(str(current_fact.value[value_key]))
    assert current_fact.knowledge_range.lower is not None  # our own rows always set this
    knowledge_time = current_fact.knowledge_range.lower

    evaluation_key = _evaluation_key(
        rule_version_id=rule_version_id,
        trigger_type=trigger_type,
        trigger_id=trigger_id,
        knowledge_time=knowledge_time,
    )
    existing = (
        await session.execute(
            select(RuleEvaluation).where(RuleEvaluation.evaluation_key == evaluation_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return RuleEvaluationRecorded(rule_evaluation_id=existing.id, outcome=existing.outcome)

    previous = await _previous_evaluation(session, rule_version_id=rule_version_id)
    previous_value = (
        await _resolve_current_value_input(session, rule_evaluation_id=previous.id)
        if previous is not None
        else None
    )

    threshold = rule_version.threshold_value
    current_above = current_value > threshold

    if previous_value is None:
        outcome = OUTCOME_INITIAL_STATE
    else:
        previous_above = previous_value > threshold
        matched_state = (
            current_above
            if rule_version.predicate == PREDICATE_CROSSES_ABOVE
            else not current_above
        )
        was_matched_state = (
            previous_above
            if rule_version.predicate == PREDICATE_CROSSES_ABOVE
            else not previous_above
        )
        if matched_state and not was_matched_state:
            outcome = OUTCOME_MATCH
        elif matched_state and was_matched_state:
            outcome = OUTCOME_STILL_MATCHED
        else:
            outcome = OUTCOME_NO_MATCH

    evaluation = RuleEvaluation(
        account_id=rule_version.account_id,
        evaluation_key=evaluation_key,
        rule_version_id=rule_version_id,
        trigger_type=trigger_type,
        trigger_id=trigger_id,
        knowledge_time=knowledge_time,
        evaluator_version=EVALUATOR_VERSION,
        outcome=outcome,
    )
    session.add(evaluation)
    await session.flush()
    session.add(
        RuleEvaluationInput(
            account_id=rule_version.account_id,
            rule_evaluation_id=evaluation.id,
            accepted_fact_id=current_fact.id,
            role=CURRENT_VALUE_ROLE,
        )
    )

    return RuleEvaluationRecorded(rule_evaluation_id=evaluation.id, outcome=outcome)
