"""A monitoring rule can watch a calculation_result-backed metric (e.g. a
model-implied clean price), not just an accepted_fact-backed one - proves
rule_engine.py's and alerts.py's discriminated-union generalization
against real Postgres: the crossing logic itself doesn't care which truth
class it's watching, but the evidence trail and rights check must still
correctly reflect which one it actually used.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    BASIS_MODEL_IMPLIED,
    CalculationResult,
    CalculationSpecification,
)
from app.modules.calculation.pipeline.curve_pricing import METRIC_MODEL_IMPLIED_CLEAN_PRICE
from app.modules.calculation.service import CALCULATION_RIGHTS_PROFILE_CODE
from app.modules.evidence.models import EvidenceMember
from app.modules.identity import service as identity_service
from app.modules.monitoring.alerts import AlertCreated, AlertSkipped, create_alert_for_evaluation
from app.modules.monitoring.models import (
    PREDICATE_CROSSES_ABOVE,
    RULE_INPUT_KIND_CALCULATION,
    STATUS_ARMED,
    SUBJECT_TYPE_INSTRUMENT,
    Alert,
    MonitoringRule,
    MonitoringRuleVersion,
    RuleEvaluationInput,
)
from app.modules.monitoring.rule_engine import RuleEvaluationRecorded, evaluate_rule_version
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.rights.models import RightsGrant, RightsProfile

_PASSWORD = "correct-horse-9"
_SUBJECT_ID_ANCHOR = uuid.uuid4()


def _email() -> str:
    return f"calcmon-{uuid.uuid4().hex[:12]}@example.com"


async def _act_as(
    session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID
) -> None:
    await identity_service.apply_rls_context(
        session, account_id=account_id, principal_id=principal_id
    )


async def _register_tenant(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    login = await identity_service.register(session, email=_email(), password=_PASSWORD)
    await session.commit()
    await _act_as(
        session, account_id=login.identity.account_id, principal_id=login.identity.principal_id
    )
    return login.identity.account_id, login.identity.principal_id


async def _seed_governance(session: AsyncSession) -> None:
    session.add(
        CapabilityStatus(
            capability_code="monitoring.alerts.create", jurisdiction_code=None, status="AVAILABLE"
        )
    )
    session.add(
        ActivationRecord(
            jurisdiction_code="GB", operating_entity="Test Entity", status="ACTIVE",
            effective_from=dt.datetime.now(dt.UTC) - dt.timedelta(days=1), effective_to=None,
        )
    )
    await session.flush()


async def _seed_calculation_rights(session: AsyncSession, *, granted: bool = True) -> None:
    profile = RightsProfile(code=CALCULATION_RIGHTS_PROFILE_CODE, status="ACTIVE")
    session.add(profile)
    await session.flush()
    if granted:
        session.add(
            RightsGrant(rights_profile_id=profile.id, action="retrieve", permission_state="ALLOW")
        )
        await session.flush()


async def _seed_rule_version(
    session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID
) -> uuid.UUID:
    rule = MonitoringRule(account_id=account_id)
    session.add(rule)
    await session.flush()
    rule_version = MonitoringRuleVersion(
        account_id=account_id,
        rule_id=rule.id,
        version=1,
        status=STATUS_ARMED,
        subject_type=SUBJECT_TYPE_INSTRUMENT,
        subject_id=_SUBJECT_ID_ANCHOR,
        metric_id=METRIC_MODEL_IMPLIED_CLEAN_PRICE,
        predicate=PREDICATE_CROSSES_ABOVE,
        threshold_value=Decimal("90.0"),
        effective_from=dt.datetime.now(dt.UTC),
        created_by_principal_id=principal_id,
    )
    session.add(rule_version)
    await session.flush()
    rule.current_rule_version_id = rule_version.id
    return rule_version.id


async def _seed_calculation_result(
    session: AsyncSession, *, clean_price: str, as_of_date: dt.date
) -> uuid.UUID:
    spec = CalculationSpecification(
        code=f"test-spec-{uuid.uuid4().hex[:8]}", version="1", status="APPROVED",
        description="test",
    )
    session.add(spec)
    await session.flush()
    result = CalculationResult(
        calculation_specification_id=spec.id,
        subject_type=SUBJECT_TYPE_INSTRUMENT,
        subject_id=_SUBJECT_ID_ANCHOR,
        metric_id=METRIC_MODEL_IMPLIED_CLEAN_PRICE,
        as_of_date=as_of_date,
        basis=BASIS_MODEL_IMPLIED,
        value={"clean_price": clean_price},
        status="ACTIVE",
    )
    session.add(result)
    await session.flush()
    return result.id


async def test_initial_state_evaluation_records_a_calculation_kind_input(
    db_session: AsyncSession,
) -> None:
    account_id, principal_id = await _register_tenant(db_session)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await _seed_calculation_result(
        db_session, clean_price="85.00", as_of_date=dt.date(2026, 9, 10)
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    result = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type="SCHEDULED_SWEEP",
        trigger_id=None,
    )

    assert isinstance(result, RuleEvaluationRecorded)
    input_row = (
        await db_session.execute(
            RuleEvaluationInput.__table__.select().where(
                RuleEvaluationInput.rule_evaluation_id == result.rule_evaluation_id
            )
        )
    ).one()
    assert input_row.kind == RULE_INPUT_KIND_CALCULATION
    assert input_row.calculation_result_id is not None
    assert input_row.accepted_fact_id is None


async def test_crossing_a_model_implied_price_threshold_fires_match(
    db_session: AsyncSession,
) -> None:
    account_id, principal_id = await _register_tenant(db_session)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await _seed_calculation_result(
        db_session, clean_price="85.00", as_of_date=dt.date(2026, 9, 10)
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    first = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type="SCHEDULED_SWEEP",
        trigger_id=None,
    )
    assert isinstance(first, RuleEvaluationRecorded)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    await _seed_calculation_result(
        db_session, clean_price="95.00", as_of_date=dt.date(2026, 9, 11)
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    second = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type="SCHEDULED_SWEEP",
        trigger_id=None,
    )

    assert isinstance(second, RuleEvaluationRecorded)
    assert second.outcome == "MATCH"


async def test_alert_for_a_calculation_backed_evaluation_has_calculation_evidence(
    db_session: AsyncSession,
) -> None:
    account_id, principal_id = await _register_tenant(db_session)
    await _seed_governance(db_session)
    await _seed_calculation_rights(db_session)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    calc_result_id = await _seed_calculation_result(
        db_session, clean_price="85.00", as_of_date=dt.date(2026, 9, 10)
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    evaluation = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type="SCHEDULED_SWEEP",
        trigger_id=None,
    )
    assert isinstance(evaluation, RuleEvaluationRecorded)

    alert_result = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=evaluation.rule_evaluation_id
    )

    assert isinstance(alert_result, AlertCreated)
    alert = await db_session.get(Alert, alert_result.alert_id)
    assert alert is not None
    assert alert.observed_value == Decimal("85.00")

    member = (
        await db_session.execute(
            EvidenceMember.__table__.select().where(
                EvidenceMember.evidence_bundle_id == alert.evidence_bundle_id
            )
        )
    ).one()
    assert member.kind == "CALCULATION"
    assert member.calculation_result_id == calc_result_id


async def test_without_calculation_rights_no_alert_is_created(db_session: AsyncSession) -> None:
    account_id, principal_id = await _register_tenant(db_session)
    await _seed_governance(db_session)
    # Deliberately skip _seed_calculation_rights - fail-closed DENY.
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await _seed_calculation_result(
        db_session, clean_price="85.00", as_of_date=dt.date(2026, 9, 10)
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    evaluation = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type="SCHEDULED_SWEEP",
        trigger_id=None,
    )
    assert isinstance(evaluation, RuleEvaluationRecorded)

    result = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=evaluation.rule_evaluation_id
    )
    assert isinstance(result, AlertSkipped)
