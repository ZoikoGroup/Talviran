"""Coverage tracking against real Postgres: record_successful_evaluation
always resets to HEALTHY and closes any open incident; check_rule_coverage
detects a lapse purely from elapsed time, independent of any new
evaluation, using METRIC_UK_GILT_NOMINAL_SPOT_CURVE's real 1-day
freshness_slo (market/freshness.py) as the expected evaluation interval.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity import service as identity_service
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    curve_point_subject_id,
)
from app.modules.monitoring.coverage import (
    CoverageChecked,
    CoverageSkipped,
    check_rule_coverage,
    record_successful_evaluation,
)
from app.modules.monitoring.models import (
    COVERAGE_STATE_AT_RISK,
    COVERAGE_STATE_HEALTHY,
    COVERAGE_STATE_LAPSED,
    COVERAGE_STATE_SUSPENDED,
    PREDICATE_CROSSES_ABOVE,
    STATUS_ARMED,
    SUBJECT_TYPE_INSTRUMENT,
    MonitoringCoverage,
    MonitoringCoverageIncident,
    MonitoringRule,
    MonitoringRuleVersion,
    RuleEvaluation,
)

_TENOR = Decimal("10")
_SUBJECT_ID = curve_point_subject_id(_TENOR)
_ONE_DAY = dt.timedelta(days=1)


async def _act_as(session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID) -> None:
    await identity_service.apply_rls_context(
        session, account_id=account_id, principal_id=principal_id
    )


async def _seed_rule_version(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    principal_id: uuid.UUID,
    effective_from: dt.datetime,
) -> MonitoringRuleVersion:
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
        effective_from=effective_from,
        created_by_principal_id=principal_id,
    )
    session.add(rule_version)
    await session.flush()
    rule.current_rule_version_id = rule_version.id
    return rule_version


async def _seed_evaluation(
    session: AsyncSession,
    *,
    rule_version: MonitoringRuleVersion,
    evaluated_at: dt.datetime,
) -> uuid.UUID:
    evaluation = RuleEvaluation(
        account_id=rule_version.account_id,
        evaluation_key=uuid.uuid4().hex,
        rule_version_id=rule_version.id,
        trigger_type="FACT_PUBLISHED",
        trigger_id=None,
        knowledge_time=evaluated_at,
        evaluator_version="crossing_v1",
        outcome="INITIAL_STATE",
        evaluated_at=evaluated_at,
    )
    session.add(evaluation)
    await session.flush()
    return evaluation.id


async def test_record_successful_evaluation_creates_a_healthy_coverage_row(
    db_session: AsyncSession,
) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version = await _seed_rule_version(
        db_session,
        account_id=account_id,
        principal_id=principal_id,
        effective_from=dt.datetime(2026, 9, 10, tzinfo=dt.UTC),
    )
    evaluation_id = await _seed_evaluation(
        db_session,
        rule_version=rule_version,
        evaluated_at=dt.datetime(2026, 9, 10, 12, tzinfo=dt.UTC),
    )

    result = await record_successful_evaluation(db_session, rule_evaluation_id=evaluation_id)

    assert isinstance(result, CoverageChecked)
    assert result.coverage_state == COVERAGE_STATE_HEALTHY
    coverage = (
        await db_session.execute(
            MonitoringCoverage.__table__.select().where(
                MonitoringCoverage.rule_id == rule_version.rule_id
            )
        )
    ).one()
    assert coverage.last_evaluation_outcome == "INITIAL_STATE"


async def test_within_interval_is_healthy(db_session: AsyncSession) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version = await _seed_rule_version(
        db_session,
        account_id=account_id,
        principal_id=principal_id,
        effective_from=dt.datetime(2026, 9, 10, tzinfo=dt.UTC),
    )
    evaluation_id = await _seed_evaluation(
        db_session,
        rule_version=rule_version,
        evaluated_at=dt.datetime(2026, 9, 10, 12, tzinfo=dt.UTC),
    )
    await record_successful_evaluation(db_session, rule_evaluation_id=evaluation_id)

    result = await check_rule_coverage(
        db_session,
        rule_id=rule_version.rule_id,
        now=dt.datetime(2026, 9, 10, 18, tzinfo=dt.UTC),  # 6h later, within the 1-day SLO
    )

    assert isinstance(result, CoverageChecked)
    assert result.coverage_state == COVERAGE_STATE_HEALTHY


async def test_beyond_interval_within_at_risk_multiple_is_at_risk(db_session: AsyncSession) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version = await _seed_rule_version(
        db_session,
        account_id=account_id,
        principal_id=principal_id,
        effective_from=dt.datetime(2026, 9, 10, tzinfo=dt.UTC),
    )
    evaluation_id = await _seed_evaluation(
        db_session,
        rule_version=rule_version,
        evaluated_at=dt.datetime(2026, 9, 10, 12, tzinfo=dt.UTC),
    )
    await record_successful_evaluation(db_session, rule_evaluation_id=evaluation_id)

    result = await check_rule_coverage(
        db_session,
        rule_id=rule_version.rule_id,
        now=dt.datetime(2026, 9, 11, 18, tzinfo=dt.UTC),  # 1.25 days later
    )

    assert isinstance(result, CoverageChecked)
    assert result.coverage_state == COVERAGE_STATE_AT_RISK


async def test_beyond_at_risk_multiple_is_lapsed_and_opens_an_incident(
    db_session: AsyncSession,
) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version = await _seed_rule_version(
        db_session,
        account_id=account_id,
        principal_id=principal_id,
        effective_from=dt.datetime(2026, 9, 10, tzinfo=dt.UTC),
    )
    evaluation_id = await _seed_evaluation(
        db_session,
        rule_version=rule_version,
        evaluated_at=dt.datetime(2026, 9, 10, 12, tzinfo=dt.UTC),
    )
    await record_successful_evaluation(db_session, rule_evaluation_id=evaluation_id)

    result = await check_rule_coverage(
        db_session,
        rule_id=rule_version.rule_id,
        now=dt.datetime(2026, 9, 13, 12, tzinfo=dt.UTC),  # 3 days later
    )

    assert isinstance(result, CoverageChecked)
    assert result.coverage_state == COVERAGE_STATE_LAPSED

    incidents = (
        await db_session.execute(
            MonitoringCoverageIncident.__table__.select().where(
                MonitoringCoverageIncident.rule_id == rule_version.rule_id
            )
        )
    ).all()
    assert len(incidents) == 1
    assert incidents[0].resolved_at is None


async def test_far_beyond_interval_is_suspended(db_session: AsyncSession) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version = await _seed_rule_version(
        db_session,
        account_id=account_id,
        principal_id=principal_id,
        effective_from=dt.datetime(2026, 9, 10, tzinfo=dt.UTC),
    )
    evaluation_id = await _seed_evaluation(
        db_session,
        rule_version=rule_version,
        evaluated_at=dt.datetime(2026, 9, 10, 12, tzinfo=dt.UTC),
    )
    await record_successful_evaluation(db_session, rule_evaluation_id=evaluation_id)

    result = await check_rule_coverage(
        db_session,
        rule_id=rule_version.rule_id,
        now=dt.datetime(2026, 9, 20, 12, tzinfo=dt.UTC),  # 10 days later
    )

    assert isinstance(result, CoverageChecked)
    assert result.coverage_state == COVERAGE_STATE_SUSPENDED


async def test_recovering_after_a_lapse_closes_the_incident(db_session: AsyncSession) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version = await _seed_rule_version(
        db_session,
        account_id=account_id,
        principal_id=principal_id,
        effective_from=dt.datetime(2026, 9, 10, tzinfo=dt.UTC),
    )
    first_eval_id = await _seed_evaluation(
        db_session,
        rule_version=rule_version,
        evaluated_at=dt.datetime(2026, 9, 10, 12, tzinfo=dt.UTC),
    )
    await record_successful_evaluation(db_session, rule_evaluation_id=first_eval_id)
    lapsed = await check_rule_coverage(
        db_session,
        rule_id=rule_version.rule_id,
        now=dt.datetime(2026, 9, 13, 12, tzinfo=dt.UTC),
    )
    assert isinstance(lapsed, CoverageChecked)
    assert lapsed.coverage_state == COVERAGE_STATE_LAPSED

    second_eval_id = await _seed_evaluation(
        db_session,
        rule_version=rule_version,
        evaluated_at=dt.datetime(2026, 9, 13, 13, tzinfo=dt.UTC),
    )
    recovered = await record_successful_evaluation(db_session, rule_evaluation_id=second_eval_id)

    assert isinstance(recovered, CoverageChecked)
    assert recovered.coverage_state == COVERAGE_STATE_HEALTHY

    incidents = (
        await db_session.execute(
            MonitoringCoverageIncident.__table__.select().where(
                MonitoringCoverageIncident.rule_id == rule_version.rule_id
            )
        )
    ).all()
    assert len(incidents) == 1
    assert incidents[0].resolved_at is not None


async def test_check_rule_coverage_skipped_when_no_coverage_row_exists(
    db_session: AsyncSession,
) -> None:
    result = await check_rule_coverage(db_session, rule_id=uuid.uuid4())
    assert isinstance(result, CoverageSkipped)


async def test_record_successful_evaluation_skipped_for_unknown_evaluation(
    db_session: AsyncSession,
) -> None:
    result = await record_successful_evaluation(db_session, rule_evaluation_id=uuid.uuid4())
    assert isinstance(result, CoverageSkipped)
