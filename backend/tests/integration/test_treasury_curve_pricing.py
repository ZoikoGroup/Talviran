"""Proves compute_and_persist_treasury_model_implied_price against real
Postgres: it reads real accepted_fact rows (Treasury reference terms + par
yield curve points, never raw reference tables), writes a real
calculation_result + calculation_input rows tagged BASIS_MODEL_IMPLIED, is
idempotent, and correctly refuses an unapproved spec and a non-priceable
security type (TIPS/Bill/FRN).
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    BASIS_MODEL_IMPLIED,
    CalculationInput,
    CalculationResult,
    CalculationSpecification,
)
from app.modules.calculation.pipeline.treasury_curve_pricing import (
    METRIC_TREASURY_MODEL_IMPLIED_CLEAN_PRICE,
    TreasuryModelImpliedPriceComputed,
    TreasuryModelImpliedPriceSkipped,
    compute_and_persist_treasury_model_implied_price,
)
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.treasury_curve_ingest import (
    METRIC_US_TREASURY_PAR_YIELD_CURVE,
    SUBJECT_TYPE_TREASURY_CURVE_POINT,
    treasury_curve_point_subject_id,
)
from app.modules.market.pipeline.treasury_securities_ingest import (
    METRIC_TREASURY_SECURITY_REFERENCE_TERMS,
)

_MATURITY = dt.date(2036, 8, 15)
_OPEN_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime(2026, 8, 15, tzinfo=dt.UTC), upper=None, bounds="[)"
)


async def _seed_spec(session: AsyncSession, *, status: str = "APPROVED") -> uuid.UUID:
    spec = CalculationSpecification(
        code=f"treasury_price_from_curve_v1.test.{uuid.uuid4().hex[:8]}", version="1",
        status=status, description="test spec",
    )
    session.add(spec)
    await session.flush()
    return spec.id


async def _seed_reference_terms(
    session: AsyncSession, *, instrument_id: uuid.UUID, security_type: str = "Note"
) -> AcceptedFact:
    fact = AcceptedFact(
        subject_type="INSTRUMENT", subject_id=instrument_id,
        metric_id=METRIC_TREASURY_SECURITY_REFERENCE_TERMS, valid_range=_OPEN_RANGE,
        knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
        value={
            "security_type": security_type, "security_term": "10-Year",
            "coupon_rate": "4.0", "maturity_date": _MATURITY.isoformat(),
            "issue_date": "2026-08-15",
        },
        status="ACTIVE",
    )
    session.add(fact)
    await session.flush()
    return fact


async def _seed_curve_point(
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
        value={"tenor_field": tenor_field, "tenor_label": tenor_field, "par_yield_pct": rate},
        status="ACTIVE",
    )
    session.add(fact)
    await session.flush()
    return fact


async def _seed_full_curve(session: AsyncSession, *, valid_day: dt.date) -> None:
    for tenor_field, rate in (
        ("BC_1YEAR", "4.70"), ("BC_2YEAR", "4.50"), ("BC_5YEAR", "4.35"),
        ("BC_10YEAR", "4.50"), ("BC_20YEAR", "4.75"), ("BC_30YEAR", "4.85"),
    ):
        await _seed_curve_point(session, tenor_field=tenor_field, rate=rate, valid_day=valid_day)


async def test_computes_and_persists_a_new_price(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    reference_fact = await _seed_reference_terms(db_session, instrument_id=instrument_id)
    as_of = dt.date(2026, 10, 26)
    await _seed_full_curve(db_session, valid_day=as_of)

    result = await compute_and_persist_treasury_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=as_of,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert isinstance(result, TreasuryModelImpliedPriceComputed)
    assert result.decision == "ACCEPTED"
    assert result.dirty_price > Decimal(0)
    # Comparing at this test's own (default, 28-digit) Decimal context
    # against values computed inside the implementation's 50-digit
    # localcontext introduces its own ~1E-27 rounding noise here - same
    # tolerance reasoning as test_gilt_price_from_curve_v1_golden.py's own
    # test_dirty_minus_accrued_equals_clean_price.
    assert abs(
        result.clean_price - (result.dirty_price - result.accrued_interest)
    ) < Decimal("1E-20")

    row = await db_session.get(CalculationResult, result.calculation_result_id)
    assert row is not None
    assert row.metric_id == METRIC_TREASURY_MODEL_IMPLIED_CLEAN_PRICE
    assert row.subject_id == instrument_id
    assert row.basis == BASIS_MODEL_IMPLIED

    inputs = (
        await db_session.execute(
            select(CalculationInput).where(CalculationInput.calculation_result_id == row.id)
        )
    ).scalars().all()
    roles = {i.role for i in inputs}
    assert "REFERENCE_TERMS" in roles
    assert "CURVE_POINT" in roles
    assert any(i.accepted_fact_id == reference_fact.id for i in inputs)


async def test_recompute_with_same_inputs_is_no_change(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    as_of = dt.date(2026, 10, 26)
    await _seed_full_curve(db_session, valid_day=as_of)

    first = await compute_and_persist_treasury_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=as_of,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()
    second = await compute_and_persist_treasury_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=as_of,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert isinstance(first, TreasuryModelImpliedPriceComputed)
    assert isinstance(second, TreasuryModelImpliedPriceComputed)
    assert second.decision == "NO_CHANGE"
    assert second.calculation_result_id == first.calculation_result_id


async def test_draft_spec_is_refused_before_any_computation(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session, status="DRAFT")
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    as_of = dt.date(2026, 10, 26)
    await _seed_full_curve(db_session, valid_day=as_of)

    result = await compute_and_persist_treasury_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=as_of,
        calculation_specification_id=spec_id,
    )

    assert isinstance(result, TreasuryModelImpliedPriceSkipped)
    assert "not APPROVED" in result.reason


async def test_missing_curve_is_skipped_not_guessed(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    # No curve points seeded at all.

    result = await compute_and_persist_treasury_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=dt.date(2026, 10, 26),
        calculation_specification_id=spec_id,
    )

    assert isinstance(result, TreasuryModelImpliedPriceSkipped)
    assert "curve" in result.reason


async def test_tips_is_skipped_not_priced_under_the_wrong_methodology(
    db_session: AsyncSession,
) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id, security_type="TIPS")
    as_of = dt.date(2026, 10, 26)
    await _seed_full_curve(db_session, valid_day=as_of)

    result = await compute_and_persist_treasury_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=as_of,
        calculation_specification_id=spec_id,
    )

    assert isinstance(result, TreasuryModelImpliedPriceSkipped)
    assert "not priceable" in result.reason


async def test_missing_reference_terms_is_skipped(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    as_of = dt.date(2026, 10, 26)
    await _seed_full_curve(db_session, valid_day=as_of)
    # No reference-terms fact seeded for this instrument at all.

    result = await compute_and_persist_treasury_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=as_of,
        calculation_specification_id=spec_id,
    )

    assert isinstance(result, TreasuryModelImpliedPriceSkipped)
    assert METRIC_TREASURY_SECURITY_REFERENCE_TERMS in result.reason
