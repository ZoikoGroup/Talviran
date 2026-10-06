"""Proves compute_and_persist_gilt_risk_metrics against real Postgres:
reads real accepted_fact rows (reference terms + market close price, never
a raw reference table), writes a real calculation_result + calculation_input
rows, is idempotent (NO_CHANGE on an unchanged recompute), and correctly
supersedes when inputs change — mirrors test_calculation_curve_pricing_
service.py's own structure, the only other wired calc spec.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    BASIS_OBSERVED_YIELD_DERIVED,
    CalculationInput,
    CalculationResult,
    CalculationSpecification,
)
from app.modules.calculation.pipeline.gilt_risk_metrics_pricing import (
    METRIC_GILT_RISK_METRICS,
    GiltRiskMetricsComputed,
    GiltRiskMetricsSkipped,
    compute_and_persist_gilt_risk_metrics,
)
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS
from app.modules.market.pipeline.tradeweb_price_ingest import METRIC_GILT_MARKET_CLOSE_PRICE
from app.modules.reference.models import Instrument, InstrumentAlias, Issuer

_AS_OF = dt.date(2026, 10, 6)
_MATURITY = dt.date(2036, 3, 7)
_ISIN = "GB0032452392"  # the corrected seed gilt ISIN (4 1/4% Treasury Stock 2036)
_OPEN_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime(2003, 2, 27, tzinfo=dt.UTC), upper=None, bounds="[)"
)


def _day_range(d: dt.date) -> Range[dt.datetime]:
    start = dt.datetime.combine(d, dt.time.min, tzinfo=dt.UTC)
    return Range(lower=start, upper=start + dt.timedelta(days=1), bounds="[)")


async def _seed_spec(session: AsyncSession, *, status: str = "APPROVED") -> uuid.UUID:
    spec = CalculationSpecification(
        code=f"gilt_risk_metrics_v1.test.{uuid.uuid4().hex[:8]}",
        version="1",
        status=status,
        description="test spec",
    )
    session.add(spec)
    await session.flush()
    return spec.id


async def _seed_instrument(session: AsyncSession, *, isin: str = _ISIN) -> uuid.UUID:
    """InstrumentAlias.instrument_id is a real FK to reference.instrument -
    unlike AcceptedFact/CalculationResult.subject_id, which is a plain
    (unconstrained) UUID column - so a real Issuer+Instrument row must
    exist first, not just an arbitrary uuid4().
    """
    issuer = Issuer(name="UK Debt Management Office", country_code="GB")
    session.add(issuer)
    await session.flush()
    instrument = Instrument(
        issuer_id=issuer.id,
        instrument_type="FI_SOVEREIGN",
        name="4 1/4% Treasury Stock 2036",
        currency_code="GBP",
    )
    session.add(instrument)
    await session.flush()
    session.add(
        InstrumentAlias(instrument_id=instrument.id, alias_type="ISIN", alias_value=isin)
    )
    await session.flush()
    return instrument.id


async def _seed_reference_terms(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    coupon_rate: str = "4.25",
    gilt_type: str = "CONVENTIONAL",
    redemption_date: dt.date = _MATURITY,
) -> AcceptedFact:
    fact = AcceptedFact(
        subject_type="INSTRUMENT",
        subject_id=instrument_id,
        metric_id=METRIC_GILT_REFERENCE_TERMS,
        valid_range=_OPEN_RANGE,
        knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
        value={
            "instrument_name": "4 1/4% Treasury Stock 2036",
            "gilt_type": gilt_type,
            "coupon_rate": coupon_rate,
            "redemption_date": redemption_date.isoformat(),
            "first_issue_date": "2003-02-27",
            "dividend_dates": "07-Mar and 07-Sep",
        },
        status="ACTIVE",
    )
    session.add(fact)
    await session.flush()
    return fact


async def _seed_price(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    clean_price: str = "96.25",
    as_of: dt.date = _AS_OF,
) -> AcceptedFact:
    fact = AcceptedFact(
        subject_type="INSTRUMENT",
        subject_id=instrument_id,
        metric_id=METRIC_GILT_MARKET_CLOSE_PRICE,
        valid_range=_day_range(as_of),
        knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
        value={
            "instrument_name": "4 1/4% Treasury Stock 2036",
            "instrument_type": "Conventional",
            "clean_price": clean_price,
            "dirty_price": None,
            "yield_pct": "4.50",
            "mod_duration": None,
            "accrued_interest": None,
        },
        status="ACTIVE",
    )
    session.add(fact)
    await session.flush()
    return fact


async def test_computes_and_persists_a_new_result(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)
    instrument_id = await _seed_instrument(db_session)
    reference_fact = await _seed_reference_terms(db_session, instrument_id=instrument_id)
    price_fact = await _seed_price(db_session, instrument_id=instrument_id)

    result = await compute_and_persist_gilt_risk_metrics(
        db_session,
        instrument_id=instrument_id,
        as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert isinstance(result, GiltRiskMetricsComputed)
    assert result.decision == "ACCEPTED"
    assert result.status.value == "OK"

    row = await db_session.get(CalculationResult, result.calculation_result_id)
    assert row is not None
    assert row.basis == BASIS_OBSERVED_YIELD_DERIVED
    assert row.metric_id == METRIC_GILT_RISK_METRICS
    assert row.status == "ACTIVE"
    assert row.as_of_date == _AS_OF

    outputs = row.value["outputs"]
    assert Decimal(outputs["modified_duration_full"]) > 0
    assert Decimal(outputs["dv01_full"]) > 0
    assert Decimal(outputs["convexity_full"]) > 0
    assert outputs["calculation_status"] == "OK"
    assert row.value["instrument_master"]["isin"] == _ISIN

    inputs = (
        await db_session.execute(
            select(CalculationInput).where(CalculationInput.calculation_result_id == row.id)
        )
    ).scalars().all()
    roles = {i.role for i in inputs}
    assert roles == {"REFERENCE_TERMS", "OBSERVED_PRICE"}
    accepted_fact_ids = {i.accepted_fact_id for i in inputs}
    assert accepted_fact_ids == {reference_fact.id, price_fact.id}


async def test_recompute_with_same_inputs_is_no_change(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)
    instrument_id = await _seed_instrument(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_price(db_session, instrument_id=instrument_id)

    first = await compute_and_persist_gilt_risk_metrics(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    second = await compute_and_persist_gilt_risk_metrics(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert isinstance(first, GiltRiskMetricsComputed)
    assert isinstance(second, GiltRiskMetricsComputed)
    assert second.decision == "NO_CHANGE"
    assert second.calculation_result_id == first.calculation_result_id

    rows = (
        await db_session.execute(
            select(CalculationResult).where(CalculationResult.subject_id == instrument_id)
        )
    ).scalars().all()
    assert len(rows) == 1, "NO_CHANGE must not create a second row"


async def test_changed_price_supersedes(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)
    instrument_id = await _seed_instrument(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_price(db_session, instrument_id=instrument_id, clean_price="96.25")

    first = await compute_and_persist_gilt_risk_metrics(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    existing_price = (
        await db_session.execute(
            select(AcceptedFact).where(
                AcceptedFact.subject_id == instrument_id,
                AcceptedFact.metric_id == METRIC_GILT_MARKET_CLOSE_PRICE,
            )
        )
    ).scalar_one()
    existing_price.value = {**existing_price.value, "clean_price": "99.00"}
    await db_session.commit()

    second = await compute_and_persist_gilt_risk_metrics(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert isinstance(first, GiltRiskMetricsComputed)
    assert isinstance(second, GiltRiskMetricsComputed)
    assert second.decision == "ACCEPTED"
    assert second.calculation_result_id != first.calculation_result_id

    old_row = await db_session.get(CalculationResult, first.calculation_result_id)
    new_row = await db_session.get(CalculationResult, second.calculation_result_id)
    assert old_row is not None and new_row is not None
    assert old_row.status == "SUPERSEDED"
    assert old_row.superseded_by_id == new_row.id
    assert new_row.status == "ACTIVE"


async def test_missing_reference_terms_is_skipped(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)
    instrument_id = await _seed_instrument(db_session)
    await _seed_price(db_session, instrument_id=instrument_id)

    result = await compute_and_persist_gilt_risk_metrics(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )

    assert isinstance(result, GiltRiskMetricsSkipped)
    assert METRIC_GILT_REFERENCE_TERMS in result.reason


async def test_missing_price_is_skipped(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session)
    instrument_id = await _seed_instrument(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)

    result = await compute_and_persist_gilt_risk_metrics(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )

    assert isinstance(result, GiltRiskMetricsSkipped)
    assert METRIC_GILT_MARKET_CLOSE_PRICE in result.reason


async def test_missing_isin_is_skipped(db_session: AsyncSession) -> None:
    instrument_id = uuid.uuid4()
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_price(db_session, instrument_id=instrument_id)

    result = await compute_and_persist_gilt_risk_metrics(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )

    assert isinstance(result, GiltRiskMetricsSkipped)
    assert "ISIN" in result.reason


async def test_draft_spec_is_refused_before_any_computation(db_session: AsyncSession) -> None:
    spec_id = await _seed_spec(db_session, status="DRAFT")
    instrument_id = await _seed_instrument(db_session)
    await _seed_reference_terms(db_session, instrument_id=instrument_id)
    await _seed_price(db_session, instrument_id=instrument_id)

    result = await compute_and_persist_gilt_risk_metrics(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )

    assert isinstance(result, GiltRiskMetricsSkipped)
    assert "not APPROVED" in result.reason

    persisted = (
        await db_session.execute(
            select(CalculationResult).where(CalculationResult.subject_id == instrument_id)
        )
    ).scalars().all()
    assert persisted == [], "a DRAFT spec must never produce a persisted result"


async def test_matured_instrument_is_suppressed_but_persisted(db_session: AsyncSession) -> None:
    """Table 13's "On/after redemption" row: suppress the metrics, but
    still record WHY as a real, evidenced result - not a bare skip.
    """
    instrument_id = await _seed_instrument(db_session)
    spec_id = await _seed_spec(db_session)
    past_maturity = dt.date(2020, 3, 7)
    await _seed_reference_terms(
        db_session, instrument_id=instrument_id, redemption_date=past_maturity
    )
    await _seed_price(db_session, instrument_id=instrument_id)

    result = await compute_and_persist_gilt_risk_metrics(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert isinstance(result, GiltRiskMetricsComputed)
    assert result.decision == "ACCEPTED"
    assert result.status.value == "MATURED"

    row = await db_session.get(CalculationResult, result.calculation_result_id)
    assert row is not None
    outputs = row.value["outputs"]
    assert outputs["calculation_status"] == "MATURED"
    assert Decimal(outputs["modified_duration_full"]) == 0


async def test_ineligible_gilt_type_is_suppressed_but_persisted(db_session: AsyncSession) -> None:
    """Table 13's "Ineligible structure" row - index-linked gilts and
    STRIPS are out of scope for v1 (TAL-FI-GILT-001 Section 3.1).
    """
    instrument_id = await _seed_instrument(db_session)
    spec_id = await _seed_spec(db_session)
    await _seed_reference_terms(
        db_session, instrument_id=instrument_id, gilt_type="INDEX_LINKED"
    )
    await _seed_price(db_session, instrument_id=instrument_id)

    result = await compute_and_persist_gilt_risk_metrics(
        db_session, instrument_id=instrument_id, as_of_date=_AS_OF,
        calculation_specification_id=spec_id,
    )
    await db_session.commit()

    assert isinstance(result, GiltRiskMetricsComputed)
    assert result.decision == "ACCEPTED"
    assert result.status.value == "NOT_COVERED_BY_METHOD_V1"

    row = await db_session.get(CalculationResult, result.calculation_result_id)
    assert row is not None
    assert row.value["outputs"]["calculation_status"] == "NOT_COVERED_BY_METHOD_V1"
