"""Proves rerun_for_new_specification_version against real Postgres: a
methodology version bump produces new ACTIVE calculation_result rows under
the new spec without touching the previous version's rows at all (per
calculation/models.py's own docstring - different spec versions
legitimately coexist, this is not a supersession).
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import CalculationResult, CalculationSpecification
from app.modules.calculation.pipeline.curve_pricing import (
    ModelImpliedPriceComputed,
    compute_and_persist_model_implied_price,
)
from app.modules.calculation.pipeline.rerun import (
    RerunRefused,
    rerun_for_new_specification_version,
)
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS

_AS_OF = dt.date(2026, 9, 14)
_MATURITY = dt.date(2036, 3, 7)
_OPEN_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime(2003, 2, 27, tzinfo=dt.UTC), upper=None, bounds="[)"
)
_CURVE_DAY_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime(2026, 9, 14, tzinfo=dt.UTC),
    upper=dt.datetime(2026, 9, 15, tzinfo=dt.UTC),
    bounds="[)",
)
_FLAT_CURVE = {str(t): "5.0" for t in [5, 8, 9, 9.5, 10, 10.5, 11, 15]}


async def _seed_spec(session: AsyncSession, *, status: str = "APPROVED") -> uuid.UUID:
    spec = CalculationSpecification(
        code=f"gilt_price_from_curve_v1.test.{uuid.uuid4().hex[:8]}",
        version="1",
        status=status,
        description="test spec",
    )
    session.add(spec)
    await session.flush()
    return spec.id


async def _seed_reference_terms(session: AsyncSession, *, instrument_id: uuid.UUID) -> None:
    session.add(
        AcceptedFact(
            subject_type="INSTRUMENT",
            subject_id=instrument_id,
            metric_id=METRIC_GILT_REFERENCE_TERMS,
            valid_range=_OPEN_RANGE,
            knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
            value={
                "instrument_name": "4 1/4% Treasury Stock 2036",
                "gilt_type": "CONVENTIONAL",
                "coupon_rate": "4.25",
                "redemption_date": _MATURITY.isoformat(),
                "first_issue_date": "2003-02-27",
                "dividend_dates": "07-Mar and 07-Sep",
            },
            status="ACTIVE",
        )
    )
    await session.flush()


async def _seed_curve_points(session: AsyncSession) -> None:
    for tenor, rate in _FLAT_CURVE.items():
        session.add(
            AcceptedFact(
                subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
                subject_id=curve_point_subject_id(Decimal(tenor)),
                metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
                valid_range=_CURVE_DAY_RANGE,
                knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
                value={"tenor_years": tenor, "spot_rate_pct": rate},
                status="ACTIVE",
            )
        )
    await session.flush()


async def test_rerun_produces_new_rows_without_mutating_the_old_version(
    db_session: AsyncSession,
) -> None:
    previous_spec_id = await _seed_spec(db_session)
    new_spec_id = await _seed_spec(db_session)

    instrument_a = uuid.uuid4()
    instrument_b = uuid.uuid4()
    for instrument_id in (instrument_a, instrument_b):
        await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_curve_points(db_session)

    for instrument_id in (instrument_a, instrument_b):
        first = await compute_and_persist_model_implied_price(
            db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
            calculation_specification_id=previous_spec_id,
        )
        assert isinstance(first, ModelImpliedPriceComputed)
    await db_session.commit()

    outcome = await rerun_for_new_specification_version(
        db_session,
        previous_specification_id=previous_spec_id,
        new_specification_id=new_spec_id,
    )
    await db_session.commit()

    assert not isinstance(outcome, RerunRefused)
    assert len(outcome) == 2
    for item in outcome:
        assert isinstance(item.result, ModelImpliedPriceComputed)
        assert item.result.decision == "ACCEPTED"

    new_rows = (
        await db_session.execute(
            select(CalculationResult).where(
                CalculationResult.calculation_specification_id == new_spec_id
            )
        )
    ).scalars().all()
    assert len(new_rows) == 2
    assert {row.status for row in new_rows} == {"ACTIVE"}

    old_rows = (
        await db_session.execute(
            select(CalculationResult).where(
                CalculationResult.calculation_specification_id == previous_spec_id
            )
        )
    ).scalars().all()
    assert len(old_rows) == 2
    assert {row.status for row in old_rows} == {"ACTIVE"}, (
        "a version-bump rerun must never mark the previous version's results SUPERSEDED"
    )
    assert all(row.superseded_by_id is None for row in old_rows)


async def test_rerun_refuses_when_new_spec_is_not_approved(db_session: AsyncSession) -> None:
    previous_spec_id = await _seed_spec(db_session)
    new_spec_id = await _seed_spec(db_session, status="DRAFT")
    instrument_id = uuid.uuid4()
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_curve_points(db_session)
    result = await compute_and_persist_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=previous_spec_id,
    )
    assert isinstance(result, ModelImpliedPriceComputed)
    await db_session.commit()

    outcome = await rerun_for_new_specification_version(
        db_session,
        previous_specification_id=previous_spec_id,
        new_specification_id=new_spec_id,
    )

    assert isinstance(outcome, RerunRefused)
    assert "not APPROVED" in outcome.reason

    new_rows = (
        await db_session.execute(
            select(CalculationResult).where(
                CalculationResult.calculation_specification_id == new_spec_id
            )
        )
    ).scalars().all()
    assert new_rows == []


async def test_rerun_refuses_when_ids_are_identical(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)
    outcome = await rerun_for_new_specification_version(
        db_session, previous_specification_id=spec_id, new_specification_id=spec_id,
    )
    assert isinstance(outcome, RerunRefused)
    assert "same" in outcome.reason


async def test_rerun_with_no_previous_results_is_a_noop(db_session: AsyncSession) -> None:
    previous_spec_id = await _seed_spec(db_session)
    new_spec_id = await _seed_spec(db_session)

    outcome = await rerun_for_new_specification_version(
        db_session,
        previous_specification_id=previous_spec_id,
        new_specification_id=new_spec_id,
    )

    assert outcome == []
