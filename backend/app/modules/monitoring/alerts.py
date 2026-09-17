"""Alert creation from a rule evaluation (MON-001 §13) - the link between
rule_engine.py's crossing detection and a real, user-facing, evidence-
linked alert. Gated through the same PDP every other response path is
(AllowedOutputType.USER_RULE_ALERT is one of POL-001's 8 canonical
types, built for exactly this) - a rule engine producing a MATCH is not
itself permission to show the user anything; POL-001's own doctrine
(risk: "advice creeping back in via human-authored templates") applies
here just as much as to /research.

Only MATCH and INITIAL_STATE evaluations create an alert.
STILL_MATCHED/NO_MATCH/ERROR never do - the rule is already in whatever
state it's in, or nothing happened worth telling anyone about.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import EvidenceBundle, EvidenceMember
from app.modules.market.models import AcceptedFact
from app.modules.monitoring.models import (
    ALERT_TYPE_CROSSING,
    ALERT_TYPE_INITIAL_STATE,
    OUTCOME_INITIAL_STATE,
    OUTCOME_MATCH,
    STATUS_ALERT_CREATED,
    Alert,
    MonitoringRuleVersion,
    RuleEvaluation,
    RuleEvaluationInput,
)
from app.modules.monitoring.rule_engine import CURRENT_VALUE_ROLE, SCALAR_VALUE_KEYS
from app.modules.policy.allowed_output_type import AllowedOutputType
from app.modules.policy.pdp import PolicyContext, evaluate
from app.modules.rights.engine import RightsDecision, evaluate_action
from app.modules.rights.models import RightsProfile

# Same P1-documented scope limit as evidence/service.py's gilt-facts/
# yield-curve branches: one hardcoded rights profile per metric rather
# than tracing FactObservationLink -> SourceObservation -> rights_profile_id
# for full multi-source generality.
_METRIC_RIGHTS_PROFILE_CODE: dict[str, str] = {
    "UK_GILT_NOMINAL_SPOT_CURVE": "boe.yield-curve",
}

_DEV_JURISDICTION = "GB"
MONITORING_CAPABILITY_CODE = "monitoring.alerts.create"


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


async def _display_allowed(session: AsyncSession, rights_profile_code: str) -> bool:
    profile_id = (
        await session.execute(
            select(RightsProfile.id).where(RightsProfile.code == rights_profile_code)
        )
    ).scalar_one_or_none()
    decision = await evaluate_action(session, "display", profile_id)
    return decision is RightsDecision.ALLOW


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

    rights_profile_code = _METRIC_RIGHTS_PROFILE_CODE.get(rule_version.metric_id)
    if rights_profile_code is None or not await _display_allowed(session, rights_profile_code):
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

    fact = await session.get(AcceptedFact, input_row.accepted_fact_id)
    value_key = SCALAR_VALUE_KEYS.get(rule_version.metric_id) if fact is not None else None
    if fact is None or value_key is None:
        return AlertSkipped(reason="could not resolve the observed value's source fact")
    observed_value = Decimal(str(fact.value[value_key]))

    bundle = EvidenceBundle(
        purpose_type="MONITORING_ALERT", knowledge_time=evaluation.knowledge_time
    )
    session.add(bundle)
    await session.flush()
    session.add(
        EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=fact.id)
    )

    alert_type = (
        ALERT_TYPE_INITIAL_STATE if evaluation.outcome == OUTCOME_INITIAL_STATE
        else ALERT_TYPE_CROSSING
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
        status=STATUS_ALERT_CREATED,
    )
    session.add(alert)
    await session.flush()
    return AlertCreated(alert_id=alert.id)
