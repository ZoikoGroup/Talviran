"""evaluate_rule_version against real Postgres, including real RLS: rules
are user-owned (unlike reference/calculation data), so every insert here
must go through identity_service.apply_rls_context first, exactly like
research.* tests already do - a monitoring_rule insert with no RLS context
set is expected to fail the table's own WITH CHECK policy.
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity import service as identity_service
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.monitoring.models import (
    OUTCOME_INITIAL_STATE,
    OUTCOME_MATCH,
    OUTCOME_NO_MATCH,
    OUTCOME_REARMED,
    OUTCOME_STILL_MATCHED,
    PREDICATE_CROSSES_ABOVE,
    STATUS_ARMED,
    STATUS_DRAFT,
    SUBJECT_TYPE_INSTRUMENT,
    MonitoringRule,
    MonitoringRuleVersion,
    RuleEvaluation,
)
from app.modules.monitoring.rule_engine import (
    RuleEvaluationRecorded,
    RuleEvaluationSkipped,
    evaluate_rule_version,
)

_TENOR = Decimal("10")
_SUBJECT_ID = curve_point_subject_id(_TENOR)
_TRIGGER_TYPE = "FACT_PUBLISHED"


async def _act_as(
    session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID
) -> None:
    await identity_service.apply_rls_context(
        session, account_id=account_id, principal_id=principal_id
    )


async def _seed_rule_version(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    principal_id: uuid.UUID,
    threshold_value: Decimal = Decimal("5.0"),
    status: str = STATUS_ARMED,
    predicate: str = PREDICATE_CROSSES_ABOVE,
    rearm_threshold: Decimal | None = None,
) -> uuid.UUID:
    rule = MonitoringRule(account_id=account_id)
    session.add(rule)
    await session.flush()
    rule_version = MonitoringRuleVersion(
        account_id=account_id,
        rule_id=rule.id,
        version=1,
        status=status,
        subject_type=SUBJECT_TYPE_INSTRUMENT,
        subject_id=_SUBJECT_ID,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        predicate=predicate,
        threshold_value=threshold_value,
        rearm_threshold=rearm_threshold,
        effective_from=dt.datetime.now(dt.UTC),
        created_by_principal_id=principal_id,
    )
    session.add(rule_version)
    await session.flush()
    rule.current_rule_version_id = rule_version.id
    return rule_version.id


async def _seed_curve_point(
    session: AsyncSession, *, spot_rate_pct: str, valid_on: dt.date, knowledge_time: dt.datetime
) -> AcceptedFact:
    fact = AcceptedFact(
        subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
        subject_id=_SUBJECT_ID,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        valid_range=Range(
            lower=dt.datetime.combine(valid_on, dt.time.min, tzinfo=dt.UTC),
            upper=dt.datetime.combine(valid_on + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC),
            bounds="[)",
        ),
        knowledge_range=Range(lower=knowledge_time, upper=None, bounds="[)"),
        value={"tenor_years": str(_TENOR), "spot_rate_pct": spot_rate_pct},
        status="ACTIVE",
    )
    session.add(fact)
    await session.flush()
    return fact


async def test_first_evaluation_with_no_prior_history_is_initial_state(
    db_session: AsyncSession,
) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    day1 = dt.date(2026, 9, 10)
    fact = await _seed_curve_point(
        db_session, spot_rate_pct="4.5", valid_on=day1,
        knowledge_time=dt.datetime(2026, 9, 10, 8, 0, tzinfo=dt.UTC),
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    result = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE,
        trigger_id=fact.id,
    )

    assert isinstance(result, RuleEvaluationRecorded)
    assert result.outcome == OUTCOME_INITIAL_STATE


async def test_crossing_above_threshold_on_a_later_day_is_match(db_session: AsyncSession) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id,
        threshold_value=Decimal("5.0"),
    )
    day1 = dt.date(2026, 9, 10)
    await _seed_curve_point(
        db_session, spot_rate_pct="4.5", valid_on=day1,
        knowledge_time=dt.datetime(2026, 9, 10, 8, 0, tzinfo=dt.UTC),
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    first = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE,
        trigger_id=None,
    )
    assert isinstance(first, RuleEvaluationRecorded)
    assert first.outcome == OUTCOME_INITIAL_STATE
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    day2 = dt.date(2026, 9, 11)
    fact2 = await _seed_curve_point(
        db_session, spot_rate_pct="5.5", valid_on=day2,
        knowledge_time=dt.datetime(2026, 9, 11, 8, 0, tzinfo=dt.UTC),
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    second = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE,
        trigger_id=fact2.id,
    )

    assert isinstance(second, RuleEvaluationRecorded)
    assert second.outcome == OUTCOME_MATCH


async def test_staying_above_threshold_is_still_matched_not_a_new_match(
    db_session: AsyncSession,
) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id,
        threshold_value=Decimal("5.0"),
    )
    for day, rate in [(10, "5.5"), (11, "5.6")]:
        await _seed_curve_point(
            db_session, spot_rate_pct=rate, valid_on=dt.date(2026, 9, day),
            knowledge_time=dt.datetime(2026, 9, day, 8, 0, tzinfo=dt.UTC),
        )
        await db_session.commit()
        await _act_as(db_session, account_id=account_id, principal_id=principal_id)
        result = await evaluate_rule_version(
            db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE,
            trigger_id=None,
        )
        await db_session.commit()
        await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    assert isinstance(result, RuleEvaluationRecorded)
    assert result.outcome == OUTCOME_STILL_MATCHED


async def test_staying_below_threshold_is_no_match(db_session: AsyncSession) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id,
        threshold_value=Decimal("5.0"),
    )
    for day, rate in [(10, "4.0"), (11, "4.1")]:
        await _seed_curve_point(
            db_session, spot_rate_pct=rate, valid_on=dt.date(2026, 9, day),
            knowledge_time=dt.datetime(2026, 9, day, 8, 0, tzinfo=dt.UTC),
        )
        await db_session.commit()
        await _act_as(db_session, account_id=account_id, principal_id=principal_id)
        result = await evaluate_rule_version(
            db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE,
            trigger_id=None,
        )
        await db_session.commit()
        await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    assert isinstance(result, RuleEvaluationRecorded)
    assert result.outcome == OUTCOME_NO_MATCH


async def test_replaying_the_same_trigger_and_knowledge_time_is_idempotent(
    db_session: AsyncSession,
) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    fact = await _seed_curve_point(
        db_session, spot_rate_pct="4.5", valid_on=dt.date(2026, 9, 10),
        knowledge_time=dt.datetime(2026, 9, 10, 8, 0, tzinfo=dt.UTC),
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    first = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE,
        trigger_id=fact.id,
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    second = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE,
        trigger_id=fact.id,
    )

    assert isinstance(first, RuleEvaluationRecorded)
    assert isinstance(second, RuleEvaluationRecorded)
    assert first.rule_evaluation_id == second.rule_evaluation_id, (
        "same rule_version + trigger + knowledge_time + evaluator_version "
        "must never produce a second row (MON-001 §7.1)"
    )


async def test_non_armed_rule_is_refused(db_session: AsyncSession) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id, status=STATUS_DRAFT
    )
    await _seed_curve_point(
        db_session, spot_rate_pct="4.5", valid_on=dt.date(2026, 9, 10),
        knowledge_time=dt.datetime(2026, 9, 10, 8, 0, tzinfo=dt.UTC),
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    result = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE,
        trigger_id=None,
    )

    assert isinstance(result, RuleEvaluationSkipped)
    assert "not ARMED" in result.reason
    count = (
        await db_session.execute(
            RuleEvaluation.__table__.select().where(
                RuleEvaluation.rule_version_id == rule_version_id
            )
        )
    ).all()
    assert count == [], "a non-ARMED rule must never persist an evaluation row"


async def test_no_current_fact_is_skipped_not_a_crash(db_session: AsyncSession) -> None:
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id
    )
    await db_session.commit()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)

    result = await evaluate_rule_version(
        db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE, trigger_id=None,
    )

    assert isinstance(result, RuleEvaluationSkipped)
    assert "no value at all yet" in result.reason


async def test_hysteresis_worked_example_matches_mon_001_section_8_1(
    db_session: AsyncSession,
) -> None:
    """threshold=4.50%, rearm_threshold=4.45% - the exact worked example
    from MON-001 §8.1, reproduced value-for-value and outcome-for-outcome:
    a single fire at the first real crossing, no re-fire while wobbling in
    the dead zone (STILL_MATCHED absorbs it), REARMED only once the value
    drops below rearm_threshold, and a fresh MATCH only on the next real
    crossing after that.
    """
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version_id = await _seed_rule_version(
        db_session,
        account_id=account_id,
        principal_id=principal_id,
        threshold_value=Decimal("4.50"),
        rearm_threshold=Decimal("4.45"),
    )

    sequence = [
        ("4.44", OUTCOME_INITIAL_STATE),
        ("4.47", OUTCOME_NO_MATCH),
        ("4.51", OUTCOME_MATCH),
        ("4.49", OUTCOME_STILL_MATCHED),
        ("4.44", OUTCOME_REARMED),
        ("4.53", OUTCOME_MATCH),
    ]

    for day, (rate, expected_outcome) in enumerate(sequence, start=10):
        await _seed_curve_point(
            db_session, spot_rate_pct=rate, valid_on=dt.date(2026, 9, day),
            knowledge_time=dt.datetime(2026, 9, day, 8, 0, tzinfo=dt.UTC),
        )
        await db_session.commit()
        await _act_as(db_session, account_id=account_id, principal_id=principal_id)

        result = await evaluate_rule_version(
            db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE,
            trigger_id=None,
        )
        await db_session.commit()
        await _act_as(db_session, account_id=account_id, principal_id=principal_id)

        assert isinstance(result, RuleEvaluationRecorded), (rate, expected_outcome)
        assert result.outcome == expected_outcome, (rate, expected_outcome, result.outcome)


async def test_without_rearm_threshold_every_crossing_still_fires(
    db_session: AsyncSession,
) -> None:
    """No hysteresis configured (rearm_threshold=None) must behave exactly
    as it did before this feature existed - a wobble back above the
    threshold fires MATCH again immediately, no dead zone.
    """
    account_id, principal_id = uuid.uuid4(), uuid.uuid4()
    await _act_as(db_session, account_id=account_id, principal_id=principal_id)
    rule_version_id = await _seed_rule_version(
        db_session, account_id=account_id, principal_id=principal_id,
        threshold_value=Decimal("4.50"),
    )

    sequence = [
        ("4.44", OUTCOME_INITIAL_STATE),
        ("4.51", OUTCOME_MATCH),
        ("4.49", OUTCOME_NO_MATCH),
        ("4.53", OUTCOME_MATCH),
    ]
    for day, (rate, expected_outcome) in enumerate(sequence, start=10):
        await _seed_curve_point(
            db_session, spot_rate_pct=rate, valid_on=dt.date(2026, 9, day),
            knowledge_time=dt.datetime(2026, 9, day, 8, 0, tzinfo=dt.UTC),
        )
        await db_session.commit()
        await _act_as(db_session, account_id=account_id, principal_id=principal_id)

        result = await evaluate_rule_version(
            db_session, rule_version_id=rule_version_id, trigger_type=_TRIGGER_TYPE,
            trigger_id=None,
        )
        await db_session.commit()
        await _act_as(db_session, account_id=account_id, principal_id=principal_id)

        assert isinstance(result, RuleEvaluationRecorded), (rate, expected_outcome)
        assert result.outcome == expected_outcome, (rate, expected_outcome, result.outcome)


async def test_insert_without_rls_context_is_rejected(db_session: AsyncSession) -> None:
    # No _act_as() call - the WITH CHECK policy must refuse this insert,
    # exactly as it already does for research.* tables.
    with pytest.raises(DBAPIError):
        db_session.add(MonitoringRule(account_id=uuid.uuid4()))
        await db_session.flush()
