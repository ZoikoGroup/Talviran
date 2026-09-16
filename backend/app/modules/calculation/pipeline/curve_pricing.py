"""Persists calculation.calculation_result rows for
gilt_price_from_curve_v1 — the missing link between the pure pricing
function (specs/gilt_price_from_curve_v1/implementation.py) and a real,
queryable, evidence-linkable result.

Every input this reads is a market.accepted_fact, never a raw reference
table or source_observation directly (calculation.models' own docstring:
"a calculation must be traceable to reconciled truth") — the instrument's
coupon/maturity come from its GILT_REFERENCE_TERMS accepted_fact, and each
curve point comes from its own YIELD_CURVE_POINT accepted_fact. Both get
recorded as calculation_input rows so a result's evidence trail is
reconstructable later.

This module does not create calculation_specification rows — that's a
governance-sanctioned registration step (seed_dev.py in development),
never something compute-time code does unilaterally (calculation/models.py:
"status... is a record of that decision, not something the app can set
unilaterally at compute time").
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    BASIS_MODEL_IMPLIED,
    CalculationInput,
    CalculationResult,
    CalculationSupersession,
)
from app.modules.calculation.specs.gilt_price_from_curve_v1.implementation import (
    CurvePoint,
    model_implied_price,
)
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
)
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS

METRIC_MODEL_IMPLIED_CLEAN_PRICE = "MODEL_IMPLIED_CLEAN_PRICE"


@dataclass(frozen=True)
class ModelImpliedPriceSkipped:
    reason: str


@dataclass(frozen=True)
class ModelImpliedPriceComputed:
    calculation_result_id: uuid.UUID
    decision: str  # ACCEPTED | NO_CHANGE
    dirty_price: Decimal
    accrued_interest: Decimal
    clean_price: Decimal


async def _accepted_fact_at(
    session: AsyncSession, *, subject_id: uuid.UUID, metric_id: str, at: dt.datetime
) -> AcceptedFact | None:
    return (
        await session.execute(
            select(AcceptedFact).where(
                AcceptedFact.subject_id == subject_id,
                AcceptedFact.metric_id == metric_id,
                AcceptedFact.status == "ACTIVE",
                AcceptedFact.valid_range.contains(at),
            )
        )
    ).scalar_one_or_none()


async def _all_curve_point_facts_at(
    session: AsyncSession, *, at: dt.datetime
) -> list[AcceptedFact]:
    return list(
        (
            await session.execute(
                select(AcceptedFact).where(
                    AcceptedFact.subject_type == SUBJECT_TYPE_YIELD_CURVE_POINT,
                    AcceptedFact.metric_id == METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
                    AcceptedFact.status == "ACTIVE",
                    AcceptedFact.valid_range.contains(at),
                )
            )
        )
        .scalars()
        .all()
    )


async def _current_calculation_result(
    session: AsyncSession,
    *,
    calculation_specification_id: uuid.UUID,
    subject_id: uuid.UUID,
    metric_id: str,
    as_of_date: dt.date,
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


async def compute_and_persist_model_implied_price(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    as_of_date: dt.date,
    calculation_specification_id: uuid.UUID,
) -> ModelImpliedPriceComputed | ModelImpliedPriceSkipped:
    at = dt.datetime.combine(as_of_date, dt.time.min, tzinfo=dt.UTC)

    reference_fact = await _accepted_fact_at(
        session, subject_id=instrument_id, metric_id=METRIC_GILT_REFERENCE_TERMS, at=at
    )
    if reference_fact is None:
        return ModelImpliedPriceSkipped(
            reason=(
                f"no {METRIC_GILT_REFERENCE_TERMS} accepted_fact for instrument "
                f"{instrument_id} valid at {as_of_date}"
            )
        )

    curve_facts = await _all_curve_point_facts_at(session, at=at)
    if not curve_facts:
        return ModelImpliedPriceSkipped(
            reason=f"no BoE curve points published for {as_of_date}"
        )

    coupon_per_100 = Decimal(reference_fact.value["coupon_rate"])
    maturity_date = dt.date.fromisoformat(reference_fact.value["redemption_date"])
    curve = [
        CurvePoint(
            tenor_years=Decimal(fact.value["tenor_years"]),
            spot_rate_pct=Decimal(fact.value["spot_rate_pct"]),
        )
        for fact in curve_facts
    ]

    priced = model_implied_price(
        coupon_per_100=coupon_per_100,
        maturity_date=maturity_date,
        settlement_date=as_of_date,
        curve=curve,
    )
    value = {
        "dirty_price": str(priced.dirty_price),
        "accrued_interest": str(priced.accrued_interest),
        "clean_price": str(priced.clean_price),
    }

    existing = await _current_calculation_result(
        session,
        calculation_specification_id=calculation_specification_id,
        subject_id=instrument_id,
        metric_id=METRIC_MODEL_IMPLIED_CLEAN_PRICE,
        as_of_date=as_of_date,
    )

    if existing is not None and existing.value == value:
        return ModelImpliedPriceComputed(
            calculation_result_id=existing.id,
            decision="NO_CHANGE",
            dirty_price=priced.dirty_price,
            accrued_interest=priced.accrued_interest,
            clean_price=priced.clean_price,
        )

    new_result = CalculationResult(
        calculation_specification_id=calculation_specification_id,
        subject_type="INSTRUMENT",
        subject_id=instrument_id,
        metric_id=METRIC_MODEL_IMPLIED_CLEAN_PRICE,
        as_of_date=as_of_date,
        basis=BASIS_MODEL_IMPLIED,
        value=value,
        status="ACTIVE",
    )
    session.add(new_result)
    await session.flush()

    session.add(
        CalculationInput(
            calculation_result_id=new_result.id,
            accepted_fact_id=reference_fact.id,
            role="REFERENCE_TERMS",
        )
    )
    for fact in curve_facts:
        session.add(
            CalculationInput(
                calculation_result_id=new_result.id,
                accepted_fact_id=fact.id,
                role="CURVE_POINT",
            )
        )

    if existing is not None:
        existing.status = "SUPERSEDED"
        existing.superseded_by_id = new_result.id
        session.add(
            CalculationSupersession(
                old_calculation_result_id=existing.id,
                new_calculation_result_id=new_result.id,
                reason="recalculated: inputs changed since the last result for this date",
            )
        )

    return ModelImpliedPriceComputed(
        calculation_result_id=new_result.id,
        decision="ACCEPTED",
        dirty_price=priced.dirty_price,
        accrued_interest=priced.accrued_interest,
        clean_price=priced.clean_price,
    )
