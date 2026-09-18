"""Proves compute_and_persist_model_implied_price against real Postgres:
it reads real accepted_fact rows (never raw reference tables), writes a
real calculation_result + calculation_input rows, is idempotent (NO_CHANGE
on an unchanged recompute), and correctly supersedes when inputs change.
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
from app.modules.calculation.pipeline.curve_pricing import (
    METRIC_MODEL_IMPLIED_CLEAN_PRICE,
    ModelImpliedPriceComputed,
    ModelImpliedPriceSkipped,
    compute_and_persist_model_implied_price,
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


async def _seed_spec(session: AsyncSession, *, status: str = "APPROVED") -> uuid.UUID:
    # APPROVED by default: this file's other tests exercise compute/persist
    # behavior, which now correctly refuses to run at all for a DRAFT spec
    # (see test_draft_spec_is_refused_before_any_computation) - matching
    # how this function is actually called in production, always with an
    # already-approved spec id.
    spec = CalculationSpecification(
        code=f"gilt_price_from_curve_v1.test.{uuid.uuid4().hex[:8]}",
        version="1",
        status=status,
        description="test spec",
    )
    session.add(spec)
    await session.flush()
    return spec.id


async def _seed_reference_terms(
    session: AsyncSession, *, instrument_id: uuid.UUID, coupon_rate: str = "4.25"
) -> AcceptedFact:
    fact = AcceptedFact(
        subject_type="INSTRUMENT",
        subject_id=instrument_id,
        metric_id=METRIC_GILT_REFERENCE_TERMS,
        valid_range=_OPEN_RANGE,
        knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
        value={
            "instrument_name": "4 1/4% Treasury Stock 2036",
            "gilt_type": "CONVENTIONAL",
            "coupon_rate": coupon_rate,
            "redemption_date": _MATURITY.isoformat(),
            "first_issue_date": "2003-02-27",
            "dividend_dates": "07-Mar and 07-Sep",
        },
        status="ACTIVE",
    )
    session.add(fact)
    await session.flush()
    return fact


async def _seed_curve_points(
    session: AsyncSession, tenor_to_rate: dict[str, str]
) -> list[AcceptedFact]:
    facts = []
    for tenor, rate in tenor_to_rate.items():
        fact = AcceptedFact(
            subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
            subject_id=curve_point_subject_id(Decimal(tenor)),
            metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
            valid_range=_CURVE_DAY_RANGE,
            knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
            value={"tenor_years": tenor, "spot_rate_pct": rate},
            status="ACTIVE",
        )
        session.add(fact)
        facts.append(fact)
    await session.flush()
    return facts


_FLAT_CURVE = {str(t): "5.0" for t in [5, 8, 9, 9.5, 10, 10.5, 11, 15]}


async def test_computes_and_persists_a_new_result(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_curve_points(db_session, _FLAT_CURVE)

    result = await compute_and_persist_model_implied_price(
        db_session,
        instrument_id=instrument_id,
        as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert isinstance(result, ModelImpliedPriceComputed)
    assert result.decision == "ACCEPTED"
    assert result.clean_price < 100, "coupon 4.25% below flat curve yield 5% -> priced below par"

    row = await db_session.get(CalculationResult, result.calculation_result_id)
    assert row is not None
    assert row.basis == BASIS_MODEL_IMPLIED
    assert row.metric_id == METRIC_MODEL_IMPLIED_CLEAN_PRICE
    assert row.status == "ACTIVE"
    assert row.as_of_date == _AS_OF

    inputs = (
        await db_session.execute(
            select(CalculationInput).where(CalculationInput.calculation_result_id == row.id)
        )
    ).scalars().all()
    roles = {i.role for i in inputs}
    assert roles == {"REFERENCE_TERMS", "CURVE_POINT"}
    assert len([i for i in inputs if i.role == "CURVE_POINT"]) == len(_FLAT_CURVE)


async def test_recompute_with_same_inputs_is_no_change(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_curve_points(db_session, _FLAT_CURVE)

    first = await compute_and_persist_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    second = await compute_and_persist_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert isinstance(first, ModelImpliedPriceComputed)
    assert isinstance(second, ModelImpliedPriceComputed)
    assert second.decision == "NO_CHANGE"
    assert second.calculation_result_id == first.calculation_result_id

    count = (
        await db_session.execute(
            select(CalculationResult).where(CalculationResult.subject_id == instrument_id)
        )
    ).scalars().all()
    assert len(count) == 1, "NO_CHANGE must not create a second row"


async def test_changed_reference_terms_supersedes(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id, coupon_rate="4.25")
    await _seed_curve_points(db_session, _FLAT_CURVE)

    first = await compute_and_persist_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    # A correction to the reference terms (different coupon) changes the
    # computed price, so a recompute must supersede, not silently coexist.
    existing_ref = (
        await db_session.execute(
            select(AcceptedFact).where(
                AcceptedFact.subject_id == instrument_id,
                AcceptedFact.metric_id == METRIC_GILT_REFERENCE_TERMS,
            )
        )
    ).scalar_one()
    existing_ref.value = {**existing_ref.value, "coupon_rate": "5.00"}
    await db_session.commit()

    second = await compute_and_persist_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert isinstance(first, ModelImpliedPriceComputed)
    assert isinstance(second, ModelImpliedPriceComputed)
    assert second.decision == "ACCEPTED"
    assert second.calculation_result_id != first.calculation_result_id
    assert second.clean_price != first.clean_price

    old_row = await db_session.get(CalculationResult, first.calculation_result_id)
    new_row = await db_session.get(CalculationResult, second.calculation_result_id)
    assert old_row is not None and new_row is not None
    assert old_row.status == "SUPERSEDED"
    assert old_row.superseded_by_id == new_row.id
    assert new_row.status == "ACTIVE"


async def test_missing_reference_terms_is_skipped(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_curve_points(db_session, _FLAT_CURVE)

    result = await compute_and_persist_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )

    assert isinstance(result, ModelImpliedPriceSkipped)
    assert METRIC_GILT_REFERENCE_TERMS in result.reason


async def test_missing_curve_points_is_skipped(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)

    result = await compute_and_persist_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )

    assert isinstance(result, ModelImpliedPriceSkipped)
    assert "curve points" in result.reason


async def test_draft_spec_is_refused_before_any_computation(db_session: AsyncSession) -> None:
    # The whole point of the golden-test approval gate is worthless if
    # compute/persist doesn't actually check it - a DRAFT spec (never
    # verified against DMO's worked examples) must never be usable to
    # produce a real, persisted, user-visible result.
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session, status="DRAFT")
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_curve_points(db_session, _FLAT_CURVE)

    result = await compute_and_persist_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )

    assert isinstance(result, ModelImpliedPriceSkipped)
    assert "not APPROVED" in result.reason

    persisted = (
        await db_session.execute(
            select(CalculationResult).where(CalculationResult.subject_id == instrument_id)
        )
    ).scalars().all()
    assert persisted == [], "a DRAFT spec must never produce a persisted result"


async def test_deprecated_spec_is_also_refused(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session, status="DEPRECATED")
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_curve_points(db_session, _FLAT_CURVE)

    result = await compute_and_persist_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )

    assert isinstance(result, ModelImpliedPriceSkipped)


async def test_nonexistent_spec_is_refused_not_a_crash(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_curve_points(db_session, _FLAT_CURVE)

    result = await compute_and_persist_model_implied_price(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=uuid.uuid4(),
    )

    assert isinstance(result, ModelImpliedPriceSkipped)
    assert "MISSING" in result.reason
