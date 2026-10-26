"""Proves compute_and_persist_gilt_treasury_spread against real Postgres:
it reads real accepted_fact rows from BOTH curves (never raw reference
tables), writes a real calculation_result + calculation_input rows, is
idempotent (NO_CHANGE on an unchanged recompute), and correctly refuses to
compute under an unapproved spec.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    CalculationInput,
    CalculationResult,
    CalculationSpecification,
)
from app.modules.calculation.pipeline.gilt_treasury_spread_pricing import (
    METRIC_GILT_TREASURY_SPREAD,
    SpreadComputed,
    SpreadSkipped,
    compute_and_persist_gilt_treasury_spread,
    spread_subject_id,
)
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.market.pipeline.treasury_curve_ingest import (
    METRIC_US_TREASURY_PAR_YIELD_CURVE,
    SUBJECT_TYPE_TREASURY_CURVE_POINT,
    treasury_curve_point_subject_id,
)


async def _seed_spec(session: AsyncSession, *, status: str = "APPROVED") -> uuid.UUID:
    spec = CalculationSpecification(
        code=f"gilt_treasury_spread_v1.test.{uuid.uuid4().hex[:8]}", version="1",
        status=status, description="test spec",
    )
    session.add(spec)
    await session.flush()
    return spec.id


async def _seed_uk_curve_point(
    session: AsyncSession, *, tenor_years: int, rate: str, valid_day: dt.date
) -> AcceptedFact:
    valid_range: Range[dt.datetime] = Range(
        lower=dt.datetime.combine(valid_day, dt.time.min, tzinfo=dt.UTC),
        upper=dt.datetime.combine(valid_day, dt.time.min, tzinfo=dt.UTC) + dt.timedelta(days=1),
        bounds="[)",
    )
    fact = AcceptedFact(
        subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
        subject_id=curve_point_subject_id(Decimal(tenor_years)),
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE, valid_range=valid_range,
        knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
        value={"tenor_years": str(tenor_years), "spot_rate_pct": rate}, status="ACTIVE",
    )
    session.add(fact)
    await session.flush()
    return fact


async def _seed_treasury_curve_point(
    session: AsyncSession, *, tenor_field: str, rate: str, valid_day: dt.date
) -> AcceptedFact:
    valid_range: Range[dt.datetime] = Range(
        lower=dt.datetime.combine(valid_day, dt.time.min, tzinfo=dt.UTC),
        upper=dt.datetime.combine(valid_day, dt.time.min, tzinfo=dt.UTC) + dt.timedelta(days=1),
        bounds="[)",
    )
    fact = AcceptedFact(
        subject_type=SUBJECT_TYPE_TREASURY_CURVE_POINT,
        subject_id=treasury_curve_point_subject_id(tenor_field),
        metric_id=METRIC_US_TREASURY_PAR_YIELD_CURVE, valid_range=valid_range,
        knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
        value={"tenor_field": tenor_field, "tenor_label": "10 Year", "par_yield_pct": rate},
        status="ACTIVE",
    )
    session.add(fact)
    await session.flush()
    return fact


async def test_computes_and_persists_a_new_spread(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)
    await _seed_uk_curve_point(
        db_session, tenor_years=10, rate="5.3682", valid_day=dt.date(2026, 10, 21)
    )
    await _seed_treasury_curve_point(
        db_session, tenor_field="BC_10YEAR", rate="5.1300", valid_day=dt.date(2026, 10, 21)
    )

    result = await compute_and_persist_gilt_treasury_spread(
        db_session, tenor_years=10, calculation_specification_id=spec_id
    )
    await db_session.commit()

    assert isinstance(result, SpreadComputed)
    assert result.decision == "ACCEPTED"
    assert result.spread_pct == Decimal("0.2382")
    assert result.spread_bp == Decimal("23.82")

    row = await db_session.get(CalculationResult, result.calculation_result_id)
    assert row is not None
    assert row.metric_id == METRIC_GILT_TREASURY_SPREAD
    assert row.subject_id == spread_subject_id(10)
    assert row.value["uk_as_of"] == "2026-10-21"
    assert row.value["us_as_of"] == "2026-10-21"

    inputs = (
        await db_session.execute(
            select(CalculationInput).where(CalculationInput.calculation_result_id == row.id)
        )
    ).scalars().all()
    assert len(inputs) == 2
    assert {i.role for i in inputs} == {"CURVE_POINT"}


async def test_different_curve_dates_are_both_recorded_honestly(db_session: AsyncSession) -> None:
    """The real lag found live, 2026-10-22: the two curves routinely have
    different latest dates. The result must record both, never pretend
    they match.
    """
    spec_id = await _seed_spec(db_session)
    await _seed_uk_curve_point(
        db_session, tenor_years=10, rate="5.3613", valid_day=dt.date(2026, 9, 24)
    )
    await _seed_treasury_curve_point(
        db_session, tenor_field="BC_10YEAR", rate="5.1300", valid_day=dt.date(2026, 10, 21)
    )

    result = await compute_and_persist_gilt_treasury_spread(
        db_session, tenor_years=10, calculation_specification_id=spec_id
    )
    await db_session.commit()

    assert isinstance(result, SpreadComputed)
    assert result.uk_as_of == dt.date(2026, 9, 24)
    assert result.us_as_of == dt.date(2026, 10, 21)

    row = await db_session.get(CalculationResult, result.calculation_result_id)
    assert row is not None
    assert row.as_of_date == dt.date(2026, 10, 21)  # the more recent of the two


async def test_recompute_with_same_inputs_is_no_change(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)
    await _seed_uk_curve_point(
        db_session, tenor_years=10, rate="5.3682", valid_day=dt.date(2026, 10, 21)
    )
    await _seed_treasury_curve_point(
        db_session, tenor_field="BC_10YEAR", rate="5.1300", valid_day=dt.date(2026, 10, 21)
    )

    first = await compute_and_persist_gilt_treasury_spread(
        db_session, tenor_years=10, calculation_specification_id=spec_id
    )
    await db_session.commit()
    second = await compute_and_persist_gilt_treasury_spread(
        db_session, tenor_years=10, calculation_specification_id=spec_id
    )
    await db_session.commit()

    assert isinstance(first, SpreadComputed)
    assert isinstance(second, SpreadComputed)
    assert second.decision == "NO_CHANGE"
    assert second.calculation_result_id == first.calculation_result_id


async def test_draft_spec_is_refused_before_any_computation(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session, status="DRAFT")
    await _seed_uk_curve_point(
        db_session, tenor_years=10, rate="5.3682", valid_day=dt.date(2026, 10, 21)
    )
    await _seed_treasury_curve_point(
        db_session, tenor_field="BC_10YEAR", rate="5.1300", valid_day=dt.date(2026, 10, 21)
    )

    result = await compute_and_persist_gilt_treasury_spread(
        db_session, tenor_years=10, calculation_specification_id=spec_id
    )

    assert isinstance(result, SpreadSkipped)
    assert "not APPROVED" in result.reason


async def test_missing_curve_point_is_skipped_not_guessed(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)
    await _seed_uk_curve_point(
        db_session, tenor_years=10, rate="5.3682", valid_day=dt.date(2026, 10, 21)
    )
    # No Treasury curve point seeded at all.

    result = await compute_and_persist_gilt_treasury_spread(
        db_session, tenor_years=10, calculation_specification_id=spec_id
    )

    assert isinstance(result, SpreadSkipped)
    assert "Treasury" in result.reason


async def test_unsupported_tenor_is_skipped(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)

    result = await compute_and_persist_gilt_treasury_spread(
        db_session, tenor_years=3, calculation_specification_id=spec_id
    )

    assert isinstance(result, SpreadSkipped)
    assert "not one of the comparable tenors" in result.reason
