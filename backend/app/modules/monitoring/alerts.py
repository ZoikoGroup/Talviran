"""Alert creation from a rule evaluation (MON-001 §13) - the link between
rule_engine.py's crossing detection and a real, user-facing, evidence-
linked alert. Gated through the same PDP every other response path is
(AllowedOutputType.USER_RULE_ALERT is one of POL-001's 8 canonical
types, built for exactly this) - a rule engine producing a MATCH is not
itself permission to show the user anything; POL-001's own doctrine
(risk: "advice creeping back in via human-authored templates") applies
here just as much as to /research.

Only MATCH and INITIAL_STATE evaluations create an alert.
STILL_MATCHED/NO_MATCH/REARMED/ERROR never do - the rule is already in
whatever state it's in, or nothing happened worth telling anyone about.

Debounce (MON-001 §8, rule_version.debounce_seconds) is applied here, not
in the rule engine: the evaluation's own outcome stays an honest MATCH
(the crossing genuinely happened), and this layer decides whether that
MATCH should actually notify anyone. A debounced alert is still created
(status=SUPPRESSED), never silently skipped - matching this codebase's
"never silently drop a real event" doctrine elsewhere (DATA-002's own
no-silent-coercion rule for connectors).
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import CalculationResult
from app.modules.calculation.service import CALCULATION_RIGHTS_PROFILE_CODE
from app.modules.evidence.models import EvidenceBundle, EvidenceMember
from app.modules.market.models import AcceptedFact
from app.modules.monitoring.models import (
    ALERT_TYPE_CROSSING,
    ALERT_TYPE_INITIAL_STATE,
    OUTCOME_INITIAL_STATE,
    OUTCOME_MATCH,
    RULE_INPUT_KIND_CALCULATION,
    RULE_INPUT_KIND_FACT,
    STATUS_ALERT_CREATED,
    STATUS_ALERT_SUPPRESSED,
    SUPPRESSION_REASON_DEBOUNCE,
    Alert,
    AlertSuppression,
    MonitoringRuleVersion,
    RuleEvaluation,
    RuleEvaluationInput,
)
from app.modules.monitoring.rule_engine import (
    CALCULATION_SCALAR_VALUE_KEYS,
    CURRENT_VALUE_ROLE,
    SCALAR_VALUE_KEYS,
)
from app.modules.policy.allowed_output_type import AllowedOutputType
from app.modules.policy.pdp import PolicyContext, evaluate
from app.modules.rights.engine import RightsAction, RightsDecision, evaluate_action
from app.modules.rights.models import RightsProfile

# Same P1-documented scope limit as evidence/service.py's gilt-facts/
# yield-curve branches: one hardcoded rights profile per accepted_fact
# metric rather than tracing FactObservationLink -> SourceObservation ->
# rights_profile_id for full multi-source generality. "display" is the
# action, matching how vendor/licensed market data is gated elsewhere.
_METRIC_RIGHTS_PROFILE_CODE: dict[str, str] = {
    "UK_GILT_NOMINAL_SPOT_CURVE": "boe.yield-curve",
}

# calculation_result-backed metrics all share the one platform-owned
# rights profile calculation/service.py already reads results under -
# "retrieve", not "display": Talvrin's own computed output isn't licensed
# vendor content, so the display/redistribution distinction that matters
# for market data doesn't apply here.
_CALCULATION_RIGHTS_ACTION: RightsAction = "retrieve"

_DEV_JURISDICTION = "GB"
MONITORING_CAPABILITY_CODE = "monitoring.alerts.create"
DEBOUNCE_POLICY_VERSION = "debounce_v1"


@dataclass(frozen=True)
class AlertSkipped:
    reason: str


@dataclass(frozen=True)
class AlertCreated:
    alert_id: uuid.UUID


async def _pdp_permits(
    session: AsyncSession, *, principal_id: uuid.UUID, account_id: uuid.UUID
) -> bool:
    ctx = PolicyContext(
        principal_id=principal_id,
        account_id=account_id,
        jurisdiction_code=_DEV_JURISDICTION,
        capability_code=MONITORING_CAPABILITY_CODE,
        requested_output_type=AllowedOutputType.USER_RULE_ALERT,
    )
    decision = await evaluate(session, ctx)
    return decision.is_permit


async def _rights_allowed(
    session: AsyncSession, *, rights_profile_code: str, action: RightsAction
) -> bool:
    profile_id = (
        await session.execute(
            select(RightsProfile.id).where(RightsProfile.code == rights_profile_code)
        )
    ).scalar_one_or_none()
    decision = await evaluate_action(session, action, profile_id)
    return decision is RightsDecision.ALLOW


async def _is_debounced(
    session: AsyncSession, *, rule_version: MonitoringRuleVersion, knowledge_time: dt.datetime
) -> bool:
    if rule_version.debounce_seconds <= 0:
        return False
    most_recent = (
        await session.execute(
            select(Alert)
            .where(Alert.rule_version_id == rule_version.id)
            .order_by(Alert.knowledge_time.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if most_recent is None:
        return False
    elapsed = (knowledge_time - most_recent.knowledge_time).total_seconds()
    return elapsed < rule_version.debounce_seconds


async def create_alert_for_evaluation(
    session: AsyncSession, *, rule_evaluation_id: uuid.UUID
) -> AlertCreated | AlertSkipped:
    evaluation = await session.get(RuleEvaluation, rule_evaluation_id)
    if evaluation is None:
        return AlertSkipped(reason=f"no rule_evaluation {rule_evaluation_id}")

    if evaluation.outcome not in (OUTCOME_MATCH, OUTCOME_INITIAL_STATE):
        return AlertSkipped(
            reason=f"outcome {evaluation.outcome} does not warrant a new alert"
        )

    existing = (
        await session.execute(select(Alert).where(Alert.evaluation_id == rule_evaluation_id))
    ).scalar_one_or_none()
    if existing is not None:
        return AlertCreated(alert_id=existing.id)

    rule_version = await session.get(MonitoringRuleVersion, evaluation.rule_version_id)
    assert rule_version is not None  # FK guarantees this

    if not await _pdp_permits(
        session,
        principal_id=rule_version.created_by_principal_id,
        account_id=rule_version.account_id,
    ):
        return AlertSkipped(reason="policy denied USER_RULE_ALERT for this rule's account")

    if rule_version.metric_id in SCALAR_VALUE_KEYS:
        rights_profile_code = _METRIC_RIGHTS_PROFILE_CODE.get(rule_version.metric_id)
        rights_ok = rights_profile_code is not None and await _rights_allowed(
            session, rights_profile_code=rights_profile_code, action="display"
        )
    elif rule_version.metric_id in CALCULATION_SCALAR_VALUE_KEYS:
        rights_ok = await _rights_allowed(
            session,
            rights_profile_code=CALCULATION_RIGHTS_PROFILE_CODE,
            action=_CALCULATION_RIGHTS_ACTION,
        )
    else:
        rights_ok = False
    if not rights_ok:
        return AlertSkipped(
            reason=f"display not permitted for metric_id={rule_version.metric_id!r}"
        )

    input_row = (
        await session.execute(
            select(RuleEvaluationInput).where(
                RuleEvaluationInput.rule_evaluation_id == rule_evaluation_id,
                RuleEvaluationInput.role == CURRENT_VALUE_ROLE,
            )
        )
    ).scalar_one_or_none()
    if input_row is None:
        return AlertSkipped(reason="no recorded evidence input for this evaluation")

    if input_row.kind == RULE_INPUT_KIND_FACT:
        fact = (
            await session.get(AcceptedFact, input_row.accepted_fact_id)
            if input_row.accepted_fact_id is not None else None
        )
        value_key = SCALAR_VALUE_KEYS.get(rule_version.metric_id) if fact is not None else None
        if fact is None or value_key is None:
            return AlertSkipped(reason="could not resolve the observed value's source fact")
        observed_value = Decimal(str(fact.value[value_key]))
    elif input_row.kind == RULE_INPUT_KIND_CALCULATION:
        result = (
            await session.get(CalculationResult, input_row.calculation_result_id)
            if input_row.calculation_result_id is not None else None
        )
        value_key = (
            CALCULATION_SCALAR_VALUE_KEYS.get(rule_version.metric_id)
            if result is not None else None
        )
        if result is None or value_key is None:
            return AlertSkipped(
                reason="could not resolve the observed value's source calculation result"
            )
        observed_value = Decimal(str(result.value[value_key]))
    else:
        return AlertSkipped(reason=f"unknown rule_evaluation_input kind {input_row.kind!r}")

    bundle = EvidenceBundle(
        purpose_type="MONITORING_ALERT", knowledge_time=evaluation.knowledge_time
    )
    session.add(bundle)
    await session.flush()
    if input_row.kind == RULE_INPUT_KIND_FACT:
        session.add(
            EvidenceMember(
                evidence_bundle_id=bundle.id, kind="FACT",
                accepted_fact_id=input_row.accepted_fact_id,
            )
        )
    else:
        session.add(
            EvidenceMember(
                evidence_bundle_id=bundle.id, kind="CALCULATION",
                calculation_result_id=input_row.calculation_result_id,
            )
        )

    alert_type = (
        ALERT_TYPE_INITIAL_STATE if evaluation.outcome == OUTCOME_INITIAL_STATE
        else ALERT_TYPE_CROSSING
    )
    debounced = await _is_debounced(
        session, rule_version=rule_version, knowledge_time=evaluation.knowledge_time
    )
    alert = Alert(
        account_id=rule_version.account_id,
        rule_id=rule_version.rule_id,
        rule_version_id=rule_version.id,
        evaluation_id=evaluation.id,
        alert_type=alert_type,
        subject_id=rule_version.subject_id,
        metric_id=rule_version.metric_id,
        observed_value=observed_value,
        threshold_value=rule_version.threshold_value,
        knowledge_time=evaluation.knowledge_time,
        evidence_bundle_id=bundle.id,
        status=STATUS_ALERT_SUPPRESSED if debounced else STATUS_ALERT_CREATED,
    )
    session.add(alert)
    await session.flush()

    if debounced:
        session.add(
            AlertSuppression(
                account_id=rule_version.account_id,
                alert_id=alert.id,
                reason=SUPPRESSION_REASON_DEBOUNCE,
                policy_version=DEBOUNCE_POLICY_VERSION,
                started_at=evaluation.knowledge_time,
            )
        )
        await session.flush()

    return AlertCreated(alert_id=alert.id)
