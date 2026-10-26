"""Persists calculation.calculation_result rows for
gilt_treasury_spread_v1 — the missing link between the pure comparison
function (specs/gilt_treasury_spread_v1/implementation.py) and a real,
queryable, evidence-linkable result.

Every input this reads is a market.accepted_fact (never a raw reference
table), recorded as a calculation_input row so a result's evidence trail
is reconstructable later — same doctrine curve_pricing.py already follows.

Deliberately reads EACH curve's own latest value independently rather
than requiring both to share one exact date: found live, 2026-10-22, that
the UK and US curves are routinely several weeks apart in how current
their latest ingested point is (a real ingestion-cadence difference, not
a bug — see accepted_fact_as_of's own docstring for the same lag
observation). Both underlying dates are recorded in the result's own
value dict, never silently conflated into one, so a reader can see
exactly how stale either side is.
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
from app.modules.calculation.specs.gilt_treasury_spread_v1.implementation import (
    SpreadInputs,
    compute_spread,
)
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    curve_point_subject_id,
)
from app.modules.market.pipeline.treasury_curve_ingest import (
    METRIC_US_TREASURY_PAR_YIELD_CURVE,
    treasury_curve_point_subject_id,
)
from app.modules.market.queries import latest_accepted_fact

METRIC_GILT_TREASURY_SPREAD = "GILT_TREASURY_SPREAD"

#: Maps a comparable whole-year tenor to each curve's own tenor key -
#: see implementation.py's COMPARABLE_TENORS_YEARS for why only these 6.
_TREASURY_TENOR_FIELDS: dict[int, str] = {
    1: "BC_1YEAR", 2: "BC_2YEAR", 5: "BC_5YEAR",
    10: "BC_10YEAR", 20: "BC_20YEAR", 30: "BC_30YEAR",
}

_SPREAD_SUBJECT_NAMESPACE = uuid.UUID("f4d9b9e0-4e3a-4b7a-9c3a-7f2a6b1d5e8c")


def spread_subject_id(tenor_years: int) -> uuid.UUID:
    return uuid.uuid5(_SPREAD_SUBJECT_NAMESPACE, f"GILT-TREASURY-SPREAD-{tenor_years}Y")


@dataclass(frozen=True)
class SpreadSkipped:
    reason: str


@dataclass(frozen=True)
class SpreadComputed:
    calculation_result_id: uuid.UUID
    decision: str  # ACCEPTED | NO_CHANGE
    spread_pct: Decimal
    spread_bp: Decimal
    uk_as_of: dt.date
    us_as_of: dt.date


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


async def compute_and_persist_gilt_treasury_spread(
    session: AsyncSession, *, tenor_years: int, calculation_specification_id: uuid.UUID
) -> SpreadComputed | SpreadSkipped:
    # Same fail-closed doctrine as curve_pricing.py: never compute under an
    # unapproved spec, checked before any computation happens at all.
    spec = await session.get(CalculationSpecification, calculation_specification_id)
    if spec is None or spec.status != STATUS_APPROVED:
        return SpreadSkipped(
            reason=(
                f"calculation_specification {calculation_specification_id} is not "
                f"APPROVED (status={spec.status if spec is not None else 'MISSING'}) - "
                "refusing to compute or persist a result under an unvetted methodology"
            )
        )

    treasury_field = _TREASURY_TENOR_FIELDS.get(tenor_years)
    if treasury_field is None:
        comparable = sorted(_TREASURY_TENOR_FIELDS)
        return SpreadSkipped(
            reason=f"{tenor_years}Y is not one of the comparable tenors {comparable}"
        )

    uk_fact = await latest_accepted_fact(
        session,
        subject_id=curve_point_subject_id(Decimal(tenor_years)),
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    )
    if uk_fact is None:
        return SpreadSkipped(reason=f"no UK gilt curve point published yet for {tenor_years}Y")

    us_fact = await latest_accepted_fact(
        session,
        subject_id=treasury_curve_point_subject_id(treasury_field),
        metric_id=METRIC_US_TREASURY_PAR_YIELD_CURVE,
    )
    if us_fact is None:
        return SpreadSkipped(
            reason=f"no US Treasury curve point published yet for {tenor_years}Y"
        )

    result = compute_spread(
        SpreadInputs(
            uk_yield_pct=Decimal(uk_fact.value["spot_rate_pct"]),
            us_yield_pct=Decimal(us_fact.value["par_yield_pct"]),
        )
    )
    assert uk_fact.valid_range.lower is not None
    assert us_fact.valid_range.lower is not None
    uk_as_of = uk_fact.valid_range.lower.date()
    us_as_of = us_fact.valid_range.lower.date()
    as_of_date = max(uk_as_of, us_as_of)

    value = {
        "tenor_years": str(tenor_years),
        "spread_pct": str(result.spread_pct),
        "spread_bp": str(result.spread_bp),
        "uk_as_of": uk_as_of.isoformat(),
        "us_as_of": us_as_of.isoformat(),
    }
    subject_id = spread_subject_id(tenor_years)

    existing = await _current_calculation_result(
        session, calculation_specification_id=calculation_specification_id,
        subject_id=subject_id, metric_id=METRIC_GILT_TREASURY_SPREAD, as_of_date=as_of_date,
    )
    if existing is not None and existing.value == value:
        return SpreadComputed(
            calculation_result_id=existing.id, decision="NO_CHANGE",
            spread_pct=result.spread_pct, spread_bp=result.spread_bp,
            uk_as_of=uk_as_of, us_as_of=us_as_of,
        )

    new_result = CalculationResult(
        calculation_specification_id=calculation_specification_id, subject_type="SPREAD",
        subject_id=subject_id, metric_id=METRIC_GILT_TREASURY_SPREAD, as_of_date=as_of_date,
        basis=BASIS_MODEL_IMPLIED, value=value, status="ACTIVE",
    )
    session.add(new_result)
    await session.flush()

    for fact in (uk_fact, us_fact):
        session.add(
            CalculationInput(
                calculation_result_id=new_result.id, accepted_fact_id=fact.id,
                role="CURVE_POINT",
            )
        )

    if existing is not None:
        existing.status = "SUPERSEDED"
        existing.superseded_by_id = new_result.id
        session.add(
            CalculationSupersession(
                old_calculation_result_id=existing.id, new_calculation_result_id=new_result.id,
                reason=(
                    "recalculated: a newer curve point exists since the last spread "
                    "computed for this date"
                ),
            )
        )

    return SpreadComputed(
        calculation_result_id=new_result.id, decision="ACCEPTED",
        spread_pct=result.spread_pct, spread_bp=result.spread_bp,
        uk_as_of=uk_as_of, us_as_of=us_as_of,
    )
