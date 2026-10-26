"""Persists calculation.calculation_result rows for
gilt_holding_period_return_v1 — the missing link between the pure return
function (specs/gilt_holding_period_return_v1/implementation.py) and a
real, queryable, evidence-linkable result.

Scope decision: both boundary dirty prices must come from a real market
quote (GILT_MARKET_CLOSE_PRICE), never Talvrin's own model-implied
estimate. calculation.models.CalculationInput only links to an
accepted_fact, never to another calculation_result (calculation/models.py:
"a calculation must be traceable to reconciled truth, not to an
unreconciled raw candidate" - the same principle extends to not chaining
one estimate silently on top of another estimate's uncertainty). A date
with no real market quote for this instrument returns Skipped, never a
model-implied substitute.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    BASIS_OBSERVED_YIELD_DERIVED,
    STATUS_APPROVED,
    CalculationInput,
    CalculationResult,
    CalculationSpecification,
    CalculationSupersession,
)
from app.modules.calculation.specs.gilt_holding_period_return_v1.implementation import (
    HoldingPeriodInputs,
    compute_holding_period_return,
)
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS
from app.modules.market.pipeline.tradeweb_price_ingest import METRIC_GILT_MARKET_CLOSE_PRICE
from app.modules.market.queries import current_accepted_fact_at

METRIC_GILT_HOLDING_PERIOD_RETURN = "GILT_HOLDING_PERIOD_RETURN"


@dataclass(frozen=True)
class HoldingPeriodReturnSkipped:
    reason: str


@dataclass(frozen=True)
class HoldingPeriodReturnComputed:
    calculation_result_id: uuid.UUID
    decision: str  # ACCEPTED | NO_CHANGE
    coupon_payments_received: int
    income_received: Decimal
    price_return: Decimal
    total_return_amount: Decimal
    holding_period_return_pct: Decimal


async def _dirty_price_fact_at(
    session: AsyncSession, *, instrument_id: uuid.UUID, as_of_date: dt.date
) -> AcceptedFact | None:
    at = dt.datetime.combine(as_of_date, dt.time.min, tzinfo=dt.UTC)
    fact = await current_accepted_fact_at(
        session, subject_id=instrument_id, metric_id=METRIC_GILT_MARKET_CLOSE_PRICE, at=at
    )
    if fact is None or fact.value.get("dirty_price") is None:
        return None
    return fact


async def _current_calculation_result(
    session: AsyncSession, *, calculation_specification_id: uuid.UUID, subject_id: uuid.UUID,
    metric_id: str, as_of_date: dt.date,
) -> CalculationResult | None:
    return (
        await session.execute(
            select(CalculationResult).where(
                CalculationResult.calculation_specification_id == calculation_specification_id,
                CalculationResult.subject_id == subject_id,
                CalculationResult.metric_id == metric_id,
                CalculationResult.as_of_date == as_of_date,
                CalculationResult.status == "ACTIVE",
            )
        )
    ).scalar_one_or_none()


async def compute_and_persist_holding_period_return(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    start_date: dt.date,
    end_date: dt.date,
    calculation_specification_id: uuid.UUID,
) -> HoldingPeriodReturnComputed | HoldingPeriodReturnSkipped:
    spec = await session.get(CalculationSpecification, calculation_specification_id)
    if spec is None or spec.status != STATUS_APPROVED:
        return HoldingPeriodReturnSkipped(
            reason=(
                f"calculation_specification {calculation_specification_id} is not "
                f"APPROVED (status={spec.status if spec is not None else 'MISSING'}) - "
                "refusing to compute or persist a result under an unvetted methodology"
            )
        )

    if end_date <= start_date:
        return HoldingPeriodReturnSkipped(reason="end_date must be strictly after start_date")

    reference_fact = await current_accepted_fact_at(
        session, subject_id=instrument_id, metric_id=METRIC_GILT_REFERENCE_TERMS,
        at=dt.datetime.combine(end_date, dt.time.min, tzinfo=dt.UTC),
    )
    if reference_fact is None:
        return HoldingPeriodReturnSkipped(
            reason=f"no {METRIC_GILT_REFERENCE_TERMS} accepted_fact for instrument {instrument_id}"
        )

    start_fact = await _dirty_price_fact_at(
        session, instrument_id=instrument_id, as_of_date=start_date
    )
    if start_fact is None:
        return HoldingPeriodReturnSkipped(
            reason=f"no real market close price for {instrument_id} on {start_date}"
        )
    end_fact = await _dirty_price_fact_at(
        session, instrument_id=instrument_id, as_of_date=end_date
    )
    if end_fact is None:
        return HoldingPeriodReturnSkipped(
            reason=f"no real market close price for {instrument_id} on {end_date}"
        )

    coupon_per_100 = Decimal(reference_fact.value["coupon_rate"])
    maturity_date = dt.date.fromisoformat(reference_fact.value["redemption_date"])

    result = compute_holding_period_return(
        HoldingPeriodInputs(
            coupon_per_100=coupon_per_100,
            maturity_date=maturity_date,
            start_date=start_date,
            start_dirty_price=Decimal(start_fact.value["dirty_price"]),
            end_date=end_date,
            end_dirty_price=Decimal(end_fact.value["dirty_price"]),
        )
    )

    value = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "coupon_payments_received": str(result.coupon_payments_received),
        "income_received": str(result.income_received),
        "price_return": str(result.price_return),
        "total_return_amount": str(result.total_return_amount),
        "holding_period_return_pct": str(result.holding_period_return_pct),
    }

    existing = await _current_calculation_result(
        session, calculation_specification_id=calculation_specification_id,
        subject_id=instrument_id, metric_id=METRIC_GILT_HOLDING_PERIOD_RETURN,
        as_of_date=end_date,
    )
    if existing is not None and existing.value == value:
        return HoldingPeriodReturnComputed(
            calculation_result_id=existing.id, decision="NO_CHANGE",
            coupon_payments_received=result.coupon_payments_received,
            income_received=result.income_received, price_return=result.price_return,
            total_return_amount=result.total_return_amount,
            holding_period_return_pct=result.holding_period_return_pct,
        )

    new_result = CalculationResult(
        calculation_specification_id=calculation_specification_id, subject_type="INSTRUMENT",
        subject_id=instrument_id, metric_id=METRIC_GILT_HOLDING_PERIOD_RETURN,
        as_of_date=end_date, basis=BASIS_OBSERVED_YIELD_DERIVED, value=value, status="ACTIVE",
    )
    session.add(new_result)
    await session.flush()

    for fact, role in (
        (reference_fact, "REFERENCE_TERMS"),
        (start_fact, "START_PRICE"),
        (end_fact, "END_PRICE"),
    ):
        session.add(
            CalculationInput(
                calculation_result_id=new_result.id, accepted_fact_id=fact.id, role=role
            )
        )

    if existing is not None:
        existing.status = "SUPERSEDED"
        existing.superseded_by_id = new_result.id
        session.add(
            CalculationSupersession(
                old_calculation_result_id=existing.id, new_calculation_result_id=new_result.id,
                reason="recalculated: inputs changed since the last result for this date range",
            )
        )

    return HoldingPeriodReturnComputed(
        calculation_result_id=new_result.id, decision="ACCEPTED",
        coupon_payments_received=result.coupon_payments_received,
        income_received=result.income_received, price_return=result.price_return,
        total_return_amount=result.total_return_amount,
        holding_period_return_pct=result.holding_period_return_pct,
    )
