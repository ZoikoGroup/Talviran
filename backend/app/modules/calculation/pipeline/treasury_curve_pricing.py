"""Persists calculation.calculation_result rows for
treasury_price_from_curve_v1 — mirrors curve_pricing.py's shape exactly
(see that module's own docstring for the "must be traceable to reconciled
truth" reasoning this pipeline follows identically).

Scope: Notes and Bonds only (security_type in the Treasury reference-terms
value) - TIPS, Bills and FRNs are skipped with an honest reason, never
priced under a methodology that doesn't fit their shape (see
treasury_price_from_curve_v1/implementation.py's own module docstring).
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    BASIS_MODEL_IMPLIED,
    STATUS_APPROVED,
    CalculationInput,
    CalculationResult,
    CalculationSpecification,
    CalculationSupersession,
)
from app.modules.calculation.specs.treasury_price_from_curve_v1.implementation import (
    CurvePoint,
    model_implied_price,
)
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.treasury_curve_ingest import (
    METRIC_US_TREASURY_PAR_YIELD_CURVE,
    SUBJECT_TYPE_TREASURY_CURVE_POINT,
)
from app.modules.market.pipeline.treasury_securities_ingest import (
    METRIC_TREASURY_SECURITY_REFERENCE_TERMS,
)
from app.modules.market.queries import current_accepted_fact_at

METRIC_TREASURY_MODEL_IMPLIED_CLEAN_PRICE = "TREASURY_MODEL_IMPLIED_CLEAN_PRICE"

# Treasury.gov's own published par-yield curve grid (TENOR_FIELDS in
# connectors/treasury_yield_curve/mapping.py) - tenor_field has no derived
# fractional-year Decimal anywhere upstream (that module's own scope
# decision), so this pipeline owns the one place that maps a tenor_field
# string to the tenor_years a pricing curve needs.
_TENOR_FIELD_YEARS: dict[str, Decimal] = {
    "BC_1MONTH": Decimal(1) / 12,
    "BC_1_5MONTH": Decimal("1.5") / 12,
    "BC_2MONTH": Decimal(2) / 12,
    "BC_3MONTH": Decimal(3) / 12,
    "BC_4MONTH": Decimal(4) / 12,
    "BC_6MONTH": Decimal(6) / 12,
    "BC_1YEAR": Decimal(1),
    "BC_2YEAR": Decimal(2),
    "BC_3YEAR": Decimal(3),
    "BC_5YEAR": Decimal(5),
    "BC_7YEAR": Decimal(7),
    "BC_10YEAR": Decimal(10),
    "BC_20YEAR": Decimal(20),
    "BC_30YEAR": Decimal(30),
}

_PRICEABLE_SECURITY_TYPES = frozenset({"Note", "Bond"})


@dataclass(frozen=True)
class TreasuryModelImpliedPriceSkipped:
    reason: str


@dataclass(frozen=True)
class TreasuryModelImpliedPriceComputed:
    calculation_result_id: uuid.UUID
    decision: str  # ACCEPTED | NO_CHANGE
    dirty_price: Decimal
    accrued_interest: Decimal
    clean_price: Decimal


async def _all_curve_point_facts_at(
    session: AsyncSession, *, at: dt.datetime
) -> list[AcceptedFact]:
    return list(
        (
            await session.execute(
                select(AcceptedFact).where(
                    AcceptedFact.subject_type == SUBJECT_TYPE_TREASURY_CURVE_POINT,
                    AcceptedFact.metric_id == METRIC_US_TREASURY_PAR_YIELD_CURVE,
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


async def compute_and_persist_treasury_model_implied_price(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    as_of_date: dt.date,
    calculation_specification_id: uuid.UUID,
) -> TreasuryModelImpliedPriceComputed | TreasuryModelImpliedPriceSkipped:
    # Same reasoning as curve_pricing.py's identical check: a DRAFT spec
    # has not passed FIN-001's golden-test + dual-implementation gate.
    spec = await session.get(CalculationSpecification, calculation_specification_id)
    if spec is None or spec.status != STATUS_APPROVED:
        return TreasuryModelImpliedPriceSkipped(
            reason=(
                f"calculation_specification {calculation_specification_id} is not "
                f"APPROVED (status={spec.status if spec is not None else 'MISSING'}) - "
                "refusing to compute or persist a result under an unvetted methodology"
            )
        )

    at = dt.datetime.combine(as_of_date, dt.time.min, tzinfo=dt.UTC)

    reference_fact = await current_accepted_fact_at(
        session,
        subject_id=instrument_id,
        metric_id=METRIC_TREASURY_SECURITY_REFERENCE_TERMS,
        at=at,
    )
    if reference_fact is None:
        return TreasuryModelImpliedPriceSkipped(
            reason=(
                f"no {METRIC_TREASURY_SECURITY_REFERENCE_TERMS} accepted_fact for instrument "
                f"{instrument_id} valid at {as_of_date}"
            )
        )

    security_type = reference_fact.value.get("security_type")
    if security_type not in _PRICEABLE_SECURITY_TYPES:
        return TreasuryModelImpliedPriceSkipped(
            reason=(
                f"security_type={security_type!r} is not priceable by this spec "
                f"(only {sorted(_PRICEABLE_SECURITY_TYPES)} - TIPS/Bill/FRN need their own "
                "methodology, see treasury_price_from_curve_v1's own scope docstring)"
            )
        )

    curve_facts = await _all_curve_point_facts_at(session, at=at)
    if not curve_facts:
        return TreasuryModelImpliedPriceSkipped(
            reason=f"no US Treasury par-yield curve points published for {as_of_date}"
        )

    curve: list[CurvePoint] = []
    used_curve_facts: list[AcceptedFact] = []
    for fact in curve_facts:
        tenor_field = fact.value.get("tenor_field")
        tenor_years = _TENOR_FIELD_YEARS.get(tenor_field) if tenor_field else None
        if tenor_years is None:
            continue
        curve.append(
            CurvePoint(tenor_years=tenor_years, par_yield_pct=Decimal(fact.value["par_yield_pct"]))
        )
        used_curve_facts.append(fact)

    if not curve:
        return TreasuryModelImpliedPriceSkipped(
            reason=f"no recognised curve tenor fields in the {as_of_date} Treasury curve facts"
        )

    coupon_per_100 = Decimal(reference_fact.value["coupon_rate"])
    maturity_date = dt.date.fromisoformat(reference_fact.value["maturity_date"])

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
        metric_id=METRIC_TREASURY_MODEL_IMPLIED_CLEAN_PRICE,
        as_of_date=as_of_date,
    )

    if existing is not None and existing.value == value:
        return TreasuryModelImpliedPriceComputed(
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
        metric_id=METRIC_TREASURY_MODEL_IMPLIED_CLEAN_PRICE,
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
    for fact in used_curve_facts:
        session.add(
            CalculationInput(
                calculation_result_id=new_result.id, accepted_fact_id=fact.id, role="CURVE_POINT"
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

    return TreasuryModelImpliedPriceComputed(
        calculation_result_id=new_result.id,
        decision="ACCEPTED",
        dirty_price=priced.dirty_price,
        accrued_interest=priced.accrued_interest,
        clean_price=priced.clean_price,
    )
