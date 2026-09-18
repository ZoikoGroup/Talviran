"""First slice of PLT-MON-001's evaluation engine (§7): only the two
simplest predicates, CROSSES_ABOVE/CROSSES_BELOW, and only against a
single scalar value.

Hysteresis/re-arm (§8.1) IS implemented: rule_version.rearm_threshold,
when set, gates re-firing exactly as the spec's own worked example does -
a second absolute threshold the value must pass back through before a new
crossing counts as a fresh MATCH (see the state machine below). Debounce
(§8's "minimum interval between qualifying business fires") is also
implemented, but one layer up in alerts.py, not here - the evaluation's
own outcome stays an honest MATCH (the crossing genuinely happened);
whether that MATCH should actually notify anyone is a delivery-layer
decision, not an evaluation-layer one.

Deliberately NOT implemented yet (later slices, once there's a reason to
build them for real rather than guess at the shape):
  - CHANGES_BY / ENTERS_STATE / DOCUMENT_PUBLISHED / EVENT_SCHEDULED
  - BLOCKED_POLICY / BLOCKED_RIGHTS / INPUT_STALE / INPUT_UNAVAILABLE
    outcomes - no PDP/rights gate or freshness check is wired into
    evaluation itself yet (alerts.py applies PDP/rights at alert-creation
    time instead; see evidence/service.py and market/freshness.py for
    those doing the same job elsewhere)
  - automatic triggering from ingestion - this is a callable a caller
    invokes explicitly (mirrors compute_and_persist_model_implied_price's
    own P1 scope before the P2 job queue existed)

SCALAR_VALUE_KEYS/CALCULATION_SCALAR_VALUE_KEYS are this module's own
registration: PLT-MON-001 doesn't define how to pull "the one number
being watched" out of a metric's value shape (each metric's shape is
defined by its own producer, e.g. curve_ingest.py, curve_pricing.py).

Both market.accepted_fact-backed AND calculation.calculation_result-
backed metrics are supported: a rule can watch either a real published
value (e.g. one gilt-curve tenor's spot rate) or a computed one (e.g. a
model-implied clean price). RuleEvaluationInput is a discriminated union
(kind + nullable FKs, mirroring evidence.models.EvidenceMember's
identical pattern) recording which table the value actually came from -
never blurring the two truth classes together even though the crossing
logic itself doesn't care which one it's watching. Reference terms
(GILT_REFERENCE_TERMS) is a multi-field record, not a scalar, and is
never registrable in either registry regardless.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import CalculationResult
from app.modules.calculation.pipeline.curve_pricing import METRIC_MODEL_IMPLIED_CLEAN_PRICE
from app.modules.calculation.queries import latest_calculation_result
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import METRIC_UK_GILT_NOMINAL_SPOT_CURVE
from app.modules.market.queries import latest_accepted_fact
from app.modules.monitoring.models import (
    DISARMED_OUTCOMES,
    OUTCOME_INITIAL_STATE,
    OUTCOME_MATCH,
    OUTCOME_NO_MATCH,
    OUTCOME_REARMED,
    OUTCOME_STILL_MATCHED,
    PREDICATE_CROSSES_ABOVE,
    PREDICATE_CROSSES_BELOW,
    RULE_INPUT_KIND_CALCULATION,
    RULE_INPUT_KIND_FACT,
    STATUS_ARMED,
    MonitoringRuleVersion,
    RuleEvaluation,
    RuleEvaluationInput,
)

EVALUATOR_VERSION = "crossing_v1"

# accepted_fact-backed metrics: a real, directly-published/reconciled value.
SCALAR_VALUE_KEYS: dict[str, str] = {
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE: "spot_rate_pct",
}

# calculation_result-backed metrics: a computed value. A metric must never
# appear in both registries - the two truth classes are never merged, and
# nothing here tries to detect/reject that mistake beyond "whichever is
# checked first wins", so don't make it.
CALCULATION_SCALAR_VALUE_KEYS: dict[str, str] = {
    METRIC_MODEL_IMPLIED_CLEAN_PRICE: "clean_price",
}

CURRENT_VALUE_ROLE = "CURRENT_VALUE"


@dataclass(frozen=True)
class _ResolvedValue:
    value: Decimal
    knowledge_time: dt.datetime
    kind: str
    accepted_fact_id: uuid.UUID | None
    calculation_result_id: uuid.UUID | None


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


async def _resolve_current_value(
    session: AsyncSession, *, subject_id: uuid.UUID, metric_id: str
) -> _ResolvedValue | None:
    """The current value for (subject_id, metric_id), from whichever truth
    class the metric actually belongs to - never both, never guessed.
    """
    fact_value_key = SCALAR_VALUE_KEYS.get(metric_id)
    if fact_value_key is not None:
        fact = await latest_accepted_fact(session, subject_id=subject_id, metric_id=metric_id)
        if fact is None:
            return None
        assert fact.knowledge_range.lower is not None  # our own rows always set this
        return _ResolvedValue(
            value=Decimal(str(fact.value[fact_value_key])),
            knowledge_time=fact.knowledge_range.lower,
            kind=RULE_INPUT_KIND_FACT,
            accepted_fact_id=fact.id,
            calculation_result_id=None,
        )

    calc_value_key = CALCULATION_SCALAR_VALUE_KEYS.get(metric_id)
    if calc_value_key is not None:
        result = await latest_calculation_result(
            session, subject_id=subject_id, metric_id=metric_id
        )
        if result is None:
            return None
        # calculation_result has no knowledge_range - created_at (when this
        # module persisted the result) is the honest analogue of "when did
        # the platform come to know this value", the same concept
        # knowledge_time captures for an accepted_fact.
        return _ResolvedValue(
            value=Decimal(str(result.value[calc_value_key])),
            knowledge_time=result.created_at,
            kind=RULE_INPUT_KIND_CALCULATION,
            accepted_fact_id=None,
            calculation_result_id=result.id,
        )

    return None


async def _resolve_previous_value(
    session: AsyncSession, *, rule_evaluation_id: uuid.UUID
) -> Decimal | None:
    """Re-resolves the observed value a prior evaluation was based on, by
    following its recorded evidence link - never re-derived or cached
    redundantly on RuleEvaluation itself (calculation_input's own
    traceability pattern).
    """
    input_row = (
        await session.execute(
            select(RuleEvaluationInput).where(
                RuleEvaluationInput.rule_evaluation_id == rule_evaluation_id,
                RuleEvaluationInput.role == CURRENT_VALUE_ROLE,
            )
        )
    ).scalar_one_or_none()
    if input_row is None:
        return None

    if input_row.kind == RULE_INPUT_KIND_FACT:
        if input_row.accepted_fact_id is None:
            return None
        fact = await session.get(AcceptedFact, input_row.accepted_fact_id)
        if fact is None:
            return None
        value_key = SCALAR_VALUE_KEYS.get(fact.metric_id)
        return Decimal(str(fact.value[value_key])) if value_key is not None else None

    if input_row.kind == RULE_INPUT_KIND_CALCULATION:
        if input_row.calculation_result_id is None:
            return None
        result = await session.get(CalculationResult, input_row.calculation_result_id)
        if result is None:
            return None
        value_key = CALCULATION_SCALAR_VALUE_KEYS.get(result.metric_id)
        return Decimal(str(result.value[value_key])) if value_key is not None else None

    return None


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

    if (
        rule_version.metric_id not in SCALAR_VALUE_KEYS
        and rule_version.metric_id not in CALCULATION_SCALAR_VALUE_KEYS
    ):
        return RuleEvaluationSkipped(
            reason=f"no scalar value extractor registered for metric_id={rule_version.metric_id!r}"
        )

    current = await _resolve_current_value(
        session, subject_id=rule_version.subject_id, metric_id=rule_version.metric_id
    )
    if current is None:
        return RuleEvaluationSkipped(
            reason=(
                f"no value at all yet for subject_id={rule_version.subject_id} "
                f"metric_id={rule_version.metric_id!r}"
            )
        )

    current_value = current.value
    knowledge_time = current.knowledge_time

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
        await _resolve_previous_value(session, rule_evaluation_id=previous.id)
        if previous is not None
        else None
    )

    threshold = rule_version.threshold_value
    current_above = current_value > threshold
    is_above_predicate = rule_version.predicate == PREDICATE_CROSSES_ABOVE

    if previous is None or previous_value is None:
        outcome = OUTCOME_INITIAL_STATE
    elif rule_version.rearm_threshold is None:
        # No hysteresis configured - exact raw-value comparison (unchanged
        # from before rearm_threshold existed): every crossing fires.
        previous_above = previous_value > threshold
        matched_state = current_above if is_above_predicate else not current_above
        was_matched_state = previous_above if is_above_predicate else not previous_above
        if matched_state and not was_matched_state:
            outcome = OUTCOME_MATCH
        elif matched_state and was_matched_state:
            outcome = OUTCOME_STILL_MATCHED
        else:
            outcome = OUTCOME_NO_MATCH
    else:
        # Hysteresis configured (MON-001 §8.1): armed/disarmed state comes
        # from the PREVIOUS EVALUATION'S OWN OUTCOME, not from comparing
        # consecutive raw values - a wobble inside the dead zone between
        # threshold and rearm_threshold must never look like a fresh
        # crossing (STILL_MATCHED persists through it either way).
        rearm = rule_version.rearm_threshold
        if previous.outcome not in DISARMED_OUTCOMES:
            matched_state = current_above if is_above_predicate else not current_above
            outcome = OUTCOME_MATCH if matched_state else OUTCOME_NO_MATCH
        else:
            rearmed = current_value < rearm if is_above_predicate else current_value > rearm
            outcome = OUTCOME_REARMED if rearmed else OUTCOME_STILL_MATCHED

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
            kind=current.kind,
            accepted_fact_id=current.accepted_fact_id,
            calculation_result_id=current.calculation_result_id,
            role=CURRENT_VALUE_ROLE,
        )
    )

    return RuleEvaluationRecorded(rule_evaluation_id=evaluation.id, outcome=outcome)
