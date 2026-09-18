"""create_alert_for_evaluation against real Postgres: only MATCH/
INITIAL_STATE evaluations produce an alert, every alert is PDP- and
rights-gated exactly like a /research reply, and each alert carries a
real evidence bundle linking back to the same accepted_fact its
evaluation used.
"""

import datetime as dt
import uuid
from decimal import Decimal

import httpx
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import EvidenceBundle, EvidenceMember
from app.modules.identity import service as identity_service
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.monitoring.alerts import AlertCreated, AlertSkipped, create_alert_for_evaluation
from app.modules.monitoring.models import (
    ALERT_TYPE_CROSSING,
    ALERT_TYPE_INITIAL_STATE,
    PREDICATE_CROSSES_ABOVE,
    STATUS_ALERT_CREATED,
    STATUS_ALERT_SUPPRESSED,
    STATUS_ARMED,
    SUBJECT_TYPE_INSTRUMENT,
    SUPPRESSION_REASON_DEBOUNCE,
    Alert,
    AlertSuppression,
    MonitoringRule,
    MonitoringRuleVersion,
)
from app.modules.monitoring.rule_engine import RuleEvaluationRecorded, evaluate_rule_version
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.rights.models import RightsGrant, RightsProfile

_TENOR = Decimal("10")
_SUBJECT_ID = curve_point_subject_id(_TENOR)
_TRIGGER_TYPE = "FACT_PUBLISHED"


_PASSWORD = "correct-horse-9"


def _email() -> str:
    return f"mon-{uuid.uuid4().hex[:12]}@example.com"


async def _act_as(
    session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID
) -> None:
    await identity_service.apply_rls_context(
        session, account_id=account_id, principal_id=principal_id
    )


async def _register_tenant(
    session: AsyncSession, http: httpx.AsyncClient
) -> tuple[uuid.UUID, uuid.UUID]:
    """A real identity.account/principal pair - governance.policy_decision
    (written by every PDP evaluate() call) has a hard FK to identity.account,
    so a bare synthetic uuid4() satisfies monitoring's own RLS-scoped tables
    but not the PDP's own audit log.
    """
    login = await identity_service.register(
        session, email=_email(), password=_PASSWORD, http=http
    )
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


async def _seed_boe_rights(session: AsyncSession, *, granted: bool = True) -> None:
    profile = RightsProfile(code="boe.yield-curve", status="ACTIVE")
    session.add(profile)
    await session.flush()
    if granted:
        session.add(
            RightsGrant(rights_profile_id=profile.id, action="display", permission_state="ALLOW")
        )
        await session.flush()


async def _seed_rule_version(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    principal_id: uuid.UUID,
    debounce_seconds: int = 0,
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
        subject_id=_SUBJECT_ID,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        predicate=PREDICATE_CROSSES_ABOVE,
        threshold_value=Decimal("5.0"),
        debounce_seconds=debounce_seconds,
        effective_from=dt.datetime.now(dt.UTC),
        created_by_principal_id=principal_id,
    )
    session.add(rule_version)
    await session.flush()
    rule.current_rule_version_id = rule_version.id
    return rule_version.id


async def _seed_curve_point(
    session: AsyncSession, *, spot_rate_pct: str, valid_on: dt.date
) -> None:
    session.add(
        AcceptedFact(
            subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
            subject_id=_SUBJECT_ID,
            metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
            valid_range=Range(
                lower=dt.datetime.combine(valid_on, dt.time.min, tzinfo=dt.UTC),
                upper=dt.datetime.combine(
                    valid_on + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC
                ),
                bounds="[)",
            ),
            knowledge_range=Range(
                lower=dt.datetime.combine(valid_on, dt.time(8), tzinfo=dt.UTC),
                upper=None, bounds="[)",
            ),
            value={"tenor_years": str(_TENOR), "spot_rate_pct": spot_rate_pct},
            status="ACTIVE",
        )
    )
    await session.flush()


async def test_initial_state_evaluation_creates_an_initial_state_alert(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient,
) -> None:
    account_id, principal_id = await _register_tenant(db_session, supabase_http)
    await _seed_governance(db_session)
    await _seed_boe_rights(db_session)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await _seed_curve_point(db_session, spot_rate_pct="4.5", valid_on=dt.date(2026, 9, 10))
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    evaluation = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE, trigger_id=None,
    )
    assert isinstance(evaluation, RuleEvaluationRecorded)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    result = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=evaluation.rule_evaluation_id
    )

    assert isinstance(result, AlertCreated)
    alert = await db_session.get(Alert, result.alert_id)
    assert alert is not None
    assert alert.alert_type == ALERT_TYPE_INITIAL_STATE
    assert alert.observed_value == Decimal("4.5")
    assert alert.threshold_value == Decimal("5.0")

    bundle = await db_session.get(EvidenceBundle, alert.evidence_bundle_id)
    assert bundle is not None
    members = (
        await db_session.execute(
            EvidenceMember.__table__.select().where(
                EvidenceMember.evidence_bundle_id == bundle.id
            )
        )
    ).all()
    assert len(members) == 1


async def test_crossing_match_creates_a_crossing_alert(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient
) -> None:
    account_id, principal_id = await _register_tenant(db_session, supabase_http)
    await _seed_governance(db_session)
    await _seed_boe_rights(db_session)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await _seed_curve_point(db_session, spot_rate_pct="4.5", valid_on=dt.date(2026, 9, 10))
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    first_eval = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE, trigger_id=None,
    )
    assert isinstance(first_eval, RuleEvaluationRecorded)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    await _seed_curve_point(db_session, spot_rate_pct="5.5", valid_on=dt.date(2026, 9, 11))
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    second_eval = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE, trigger_id=None,
    )
    assert isinstance(second_eval, RuleEvaluationRecorded)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    result = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=second_eval.rule_evaluation_id
    )

    assert isinstance(result, AlertCreated)
    alert = await db_session.get(Alert, result.alert_id)
    assert alert is not None
    assert alert.alert_type == ALERT_TYPE_CROSSING
    assert alert.observed_value == Decimal("5.5")


async def test_calling_twice_for_the_same_evaluation_returns_the_same_alert(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient,
) -> None:
    account_id, principal_id = await _register_tenant(db_session, supabase_http)
    await _seed_governance(db_session)
    await _seed_boe_rights(db_session)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await _seed_curve_point(db_session, spot_rate_pct="4.5", valid_on=dt.date(2026, 9, 10))
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    evaluation = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE, trigger_id=None,
    )
    assert isinstance(evaluation, RuleEvaluationRecorded)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    first = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=evaluation.rule_evaluation_id
    )
    second = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=evaluation.rule_evaluation_id
    )

    assert isinstance(first, AlertCreated)
    assert isinstance(second, AlertCreated)
    assert first.alert_id == second.alert_id


async def test_without_display_rights_no_alert_is_created(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient
) -> None:
    account_id, principal_id = await _register_tenant(db_session, supabase_http)
    await _seed_governance(db_session)
    await _seed_boe_rights(db_session, granted=False)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await _seed_curve_point(db_session, spot_rate_pct="4.5", valid_on=dt.date(2026, 9, 10))
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    evaluation = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE, trigger_id=None,
    )
    assert isinstance(evaluation, RuleEvaluationRecorded)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    result = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=evaluation.rule_evaluation_id
    )

    assert isinstance(result, AlertSkipped)
    assert "display not permitted" in result.reason


async def test_pdp_denies_when_capability_is_unregistered(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient
) -> None:
    account_id, principal_id = await _register_tenant(db_session, supabase_http)
    # Deliberately skip _seed_governance - fail-closed DENY.
    await _seed_boe_rights(db_session)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await _seed_curve_point(db_session, spot_rate_pct="4.5", valid_on=dt.date(2026, 9, 10))
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    evaluation = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE, trigger_id=None,
    )
    assert isinstance(evaluation, RuleEvaluationRecorded)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    result = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=evaluation.rule_evaluation_id
    )

    assert isinstance(result, AlertSkipped)
    assert "policy denied" in result.reason


async def test_still_matched_outcome_never_creates_a_second_alert(
    db_session: AsyncSession, supabase_http: httpx.AsyncClient
) -> None:
    account_id, principal_id = await _register_tenant(db_session, supabase_http)
    await _seed_governance(db_session)
    await _seed_boe_rights(db_session)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    for day, rate in [(10, "5.5"), (11, "5.6")]:
        await _seed_curve_point(db_session, spot_rate_pct=rate, valid_on=dt.date(2026, 9, day))
        await db_session.commit()
        await _act_as(db_session, account_id=account_id, principal_id=principal_id)
        evaluation = await evaluate_rule_version(
            db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE,
            trigger_id=None,
        )
        assert isinstance(evaluation, RuleEvaluationRecorded)
        await db_session.commit()
        await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    assert isinstance(evaluation, RuleEvaluationRecorded)
    result = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=evaluation.rule_evaluation_id
    )

    assert isinstance(result, AlertSkipped)
    assert "does not warrant a new alert" in result.reason


async def test_debounce_suppresses_a_match_too_soon_after_the_last_alert(
    db_session: AsyncSession,
) -> None:
    account_id, principal_id = await _register_tenant(db_session)
    await _seed_governance(db_session)
    await _seed_boe_rights(db_session)
    # Longer than the 1-day gap between the two seeded facts below, so the
    # second (crossing) alert falls inside the debounce window.
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id,
        debounce_seconds=100_000,
    )
    await _seed_curve_point(db_session, spot_rate_pct="4.5", valid_on=dt.date(2026, 9, 10))
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    first_eval = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE, trigger_id=None,
    )
    assert isinstance(first_eval, RuleEvaluationRecorded)
    first_alert = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=first_eval.rule_evaluation_id
    )
    assert isinstance(first_alert, AlertCreated)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    await _seed_curve_point(db_session, spot_rate_pct="5.5", valid_on=dt.date(2026, 9, 11))
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    second_eval = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE, trigger_id=None,
    )
    assert isinstance(second_eval, RuleEvaluationRecorded)

    result = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=second_eval.rule_evaluation_id
    )

    assert isinstance(result, AlertCreated)
    alert = await db_session.get(Alert, result.alert_id)
    assert alert is not None
    assert alert.status == STATUS_ALERT_SUPPRESSED, (
        "a MATCH inside the debounce window must still be recorded, just not deliverable"
    )

    suppression = (
        await db_session.execute(
            AlertSuppression.__table__.select().where(AlertSuppression.alert_id == alert.id)
        )
    ).one()
    assert suppression.reason == SUPPRESSION_REASON_DEBOUNCE


async def test_debounce_does_not_suppress_after_the_window_elapses(
    db_session: AsyncSession,
) -> None:
    account_id, principal_id = await _register_tenant(db_session)
    await _seed_governance(db_session)
    await _seed_boe_rights(db_session)
    # Shorter than the 1-day gap between the two seeded facts below.
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id,
        debounce_seconds=60,
    )
    await _seed_curve_point(db_session, spot_rate_pct="4.5", valid_on=dt.date(2026, 9, 10))
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    first_eval = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE, trigger_id=None,
    )
    assert isinstance(first_eval, RuleEvaluationRecorded)
    first_alert = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=first_eval.rule_evaluation_id
    )
    assert isinstance(first_alert, AlertCreated)
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    await _seed_curve_point(db_session, spot_rate_pct="5.5", valid_on=dt.date(2026, 9, 11))
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    second_eval = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE, trigger_id=None,
    )
    assert isinstance(second_eval, RuleEvaluationRecorded)

    result = await create_alert_for_evaluation(
        db_session, rule_evaluation_id=second_eval.rule_evaluation_id
    )

    assert isinstance(result, AlertCreated)
    alert = await db_session.get(Alert, result.alert_id)
    assert alert is not None
    assert alert.status == STATUS_ALERT_CREATED
