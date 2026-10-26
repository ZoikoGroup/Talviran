"""Proves compute_and_persist_holding_period_return against real Postgres:
it reads real accepted_fact rows (reference terms + two real market close
prices, never a model-implied estimate), writes a real calculation_result
+ calculation_input rows, is idempotent, and correctly refuses both an
unapproved spec and a date with no real market quote.
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
from app.modules.calculation.pipeline.gilt_holding_period_return_pricing import (
    METRIC_GILT_HOLDING_PERIOD_RETURN,
    HoldingPeriodReturnComputed,
    HoldingPeriodReturnSkipped,
    compute_and_persist_holding_period_return,
)
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS
from app.modules.market.pipeline.tradeweb_price_ingest import METRIC_GILT_MARKET_CLOSE_PRICE

_MATURITY = dt.date(2036, 3, 7)
_OPEN_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime(2003, 2, 27, tzinfo=dt.UTC), upper=None, bounds="[)"
)


async def _seed_spec(session: AsyncSession, *, status: str = "APPROVED") -> uuid.UUID:
    spec = CalculationSpecification(
        code=f"gilt_holding_period_return_v1.test.{uuid.uuid4().hex[:8]}", version="1",
        status=status, description="test spec",
    )
    session.add(spec)
    await session.flush()
    return spec.id


async def _seed_reference_terms(session: AsyncSession, *, instrument_id: uuid.UUID) -> None:
    session.add(
        AcceptedFact(
            subject_type="INSTRUMENT", subject_id=instrument_id,
            metric_id=METRIC_GILT_REFERENCE_TERMS, valid_range=_OPEN_RANGE,
            knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
            value={
                "instrument_name": "4 1/4% Treasury Stock 2036", "gilt_type": "CONVENTIONAL",
                "coupon_rate": "4.25", "redemption_date": _MATURITY.isoformat(),
                "first_issue_date": "2003-02-27", "dividend_dates": "07-Mar and 07-Sep",
            },
            status="ACTIVE",
        )
    )
    await session.flush()


async def _seed_market_close_price(
    session: AsyncSession, *, instrument_id: uuid.UUID, trade_date: dt.date, dirty_price: str
) -> AcceptedFact:
    valid_range: Range[dt.datetime] = Range(
        lower=dt.datetime.combine(trade_date, dt.time.min, tzinfo=dt.UTC),
        upper=dt.datetime.combine(trade_date, dt.time.min, tzinfo=dt.UTC) + dt.timedelta(days=1),
        bounds="[)",
    )
    fact = AcceptedFact(
        subject_type="INSTRUMENT", subject_id=instrument_id,
        metric_id=METRIC_GILT_MARKET_CLOSE_PRICE, valid_range=valid_range,
        knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
        value={
            "instrument_name": "UKT 0.375 10/26", "instrument_type": "CONVENTIONAL",
            "clean_price": str(Decimal(dirty_price) - Decimal("0.1578")),
            "dirty_price": dirty_price, "yield_pct": "3.6880", "mod_duration": "0.0792",
            "accrued_interest": "0.1578",
        },
        status="ACTIVE",
    )
    session.add(fact)
    await session.flush()
    return fact


async def test_computes_and_persists_a_new_return(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_market_close_price(
        db_session, instrument_id=instrument_id, trade_date=dt.date(2026, 1, 1),
        dirty_price="100.00",
    )
    await _seed_market_close_price(
        db_session, instrument_id=instrument_id, trade_date=dt.date(2026, 12, 31),
        dirty_price="101.50",
    )

    result = await compute_and_persist_holding_period_return(
        db_session, instrument_id=instrument_id, start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 12, 31), calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert isinstance(result, HoldingPeriodReturnComputed)
    assert result.decision == "ACCEPTED"
    assert result.coupon_payments_received == 2
    assert result.income_received == Decimal("4.25")
    assert result.price_return == Decimal("1.50")
    assert result.total_return_amount == Decimal("5.75")
    assert result.holding_period_return_pct == Decimal("5.75")

    row = await db_session.get(CalculationResult, result.calculation_result_id)
    assert row is not None
    assert row.metric_id == METRIC_GILT_HOLDING_PERIOD_RETURN
    assert row.subject_id == instrument_id
    assert row.as_of_date == dt.date(2026, 12, 31)

    inputs = (
        await db_session.execute(
            select(CalculationInput).where(CalculationInput.calculation_result_id == row.id)
        )
    ).scalars().all()
    assert {i.role for i in inputs} == {"REFERENCE_TERMS", "START_PRICE", "END_PRICE"}


async def test_recompute_with_same_inputs_is_no_change(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_market_close_price(
        db_session, instrument_id=instrument_id, trade_date=dt.date(2026, 1, 1),
        dirty_price="100.00",
    )
    await _seed_market_close_price(
        db_session, instrument_id=instrument_id, trade_date=dt.date(2026, 12, 31),
        dirty_price="101.50",
    )

    first = await compute_and_persist_holding_period_return(
        db_session, instrument_id=instrument_id, start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 12, 31), calculation_specification_id=spec_id,
    )
    await db_session.commit()
    second = await compute_and_persist_holding_period_return(
        db_session, instrument_id=instrument_id, start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 12, 31), calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert isinstance(first, HoldingPeriodReturnComputed)
    assert isinstance(second, HoldingPeriodReturnComputed)
    assert second.decision == "NO_CHANGE"
    assert second.calculation_result_id == first.calculation_result_id


async def test_draft_spec_is_refused_before_any_computation(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session, status="DRAFT")
    await _seed_reference_terms(db_session, instrument_id=instrument_id)

    result = await compute_and_persist_holding_period_return(
        db_session, instrument_id=instrument_id, start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 12, 31), calculation_specification_id=spec_id,
    )

    assert isinstance(result, HoldingPeriodReturnSkipped)
    assert "not APPROVED" in result.reason


async def test_missing_market_price_is_skipped_not_modeled(db_session: AsyncSession) -> None:
    """The scope decision this pipeline makes real: a date with no real
    market quote returns Skipped, never silently substitutes a
    model-implied estimate.
    """
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_market_close_price(
        db_session, instrument_id=instrument_id, trade_date=dt.date(2026, 1, 1),
        dirty_price="100.00",
    )
    # No market price seeded for the end date at all.

    result = await compute_and_persist_holding_period_return(
        db_session, instrument_id=instrument_id, start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 12, 31), calculation_specification_id=spec_id,
    )

    assert isinstance(result, HoldingPeriodReturnSkipped)
    assert "no real market close price" in result.reason


async def test_end_date_not_after_start_date_is_skipped(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)

    result = await compute_and_persist_holding_period_return(
        db_session, instrument_id=instrument_id, start_date=dt.date(2026, 12, 31),
        end_date=dt.date(2026, 1, 1), calculation_specification_id=spec_id,
    )

    assert isinstance(result, HoldingPeriodReturnSkipped)
    assert "strictly after" in result.reason
