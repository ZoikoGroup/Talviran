"""Model-implied gilt pricing from the Bank of England's nominal gilt spot
curve (app/modules/market/connectors/boe_yield_curve/) — for when no real
market price/yield observation exists at all (see memory: Tradeweb's actual
per-instrument prices are legally out of reach for this platform).

This is NOT the same claim as gilt_price_yield_v1's output. That spec
converts a REAL observed yield into a price using DMO's own formula; this
spec estimates a price from a fitted, government-published curve when no
real observation exists. Every result here MUST be tagged
`BASIS_MODEL_IMPLIED` (calculation.models) and must never be written to, or
displayed as, an observed market fact — see
app/modules/calculation/models.py's module docstring and the memory note
"talvrin-model-implied-vs-market-price" for why this boundary is treated as
load-bearing, not decorative.

Method: discount the gilt's own real cash flows (from its FiSovereignTerms,
via the SAME date-schedule gilt_price_yield_v1 uses) using the BoE curve,
linearly interpolated at each cash flow's own time-to-maturity. This is a
standard zero-curve discounted-cashflow valuation, not a single-YTM
approximation — deliberately more rigorous than plugging one interpolated
curve point into gilt_price_yield_v1's YTM-based formula, since a single
YTM figure would itself already be an approximation of the curve.

Discounting deliberately reuses gilt_price_yield_v1's own period-counting
(r/s stub + integer periods thereafter), NOT an independent ACT/365.25
day-count for the curve lookup — introducing a second, different
day-count convention alongside DMO's own ACT/ACT-on-the-quasi-coupon-cycle
would make this spec's numbers subtly inconsistent with gilt_price_yield_v1
for reasons having nothing to do with real-world price differences. It's
also what lets the flat-curve consistency test (golden test suite) compare
this spec against gilt_price_yield_v1 almost exactly, rather than merely
approximately: a flat curve reduces this spec's math to gilt_price_yield_v1's
own formula term-by-term.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, localcontext

from app.modules.calculation.specs.gilt_price_yield_v1.implementation import accrued_interest
from app.modules.calculation.specs.gilt_price_yield_v1.schedule import (
    COUPONS_PER_YEAR,
    timeline_for_settlement,
)

_PRECISION = 50


@dataclass(frozen=True)
class CurvePoint:
    tenor_years: Decimal
    spot_rate_pct: Decimal


def interpolate_curve(curve: list[CurvePoint], target_tenor_years: Decimal) -> Decimal:
    """Linear interpolation between the two nearest published tenor points.
    A target outside the published range (0.5Y-40Y) clamps to the nearest
    endpoint rather than extrapolating — extrapolating a fitted curve
    beyond its own published domain is exactly the kind of silent guess
    DATA-002 doctrine forbids elsewhere in this platform; the same
    principle applies here even though this whole spec is already an
    estimate.
    """
    if not curve:
        raise ValueError("curve must have at least one point")

    ordered = sorted(curve, key=lambda p: p.tenor_years)
    if target_tenor_years <= ordered[0].tenor_years:
        return ordered[0].spot_rate_pct
    if target_tenor_years >= ordered[-1].tenor_years:
        return ordered[-1].spot_rate_pct

    for lower, upper in zip(ordered, ordered[1:], strict=False):
        if lower.tenor_years <= target_tenor_years <= upper.tenor_years:
            span = upper.tenor_years - lower.tenor_years
            weight = (target_tenor_years - lower.tenor_years) / span
            return lower.spot_rate_pct + weight * (upper.spot_rate_pct - lower.spot_rate_pct)

    raise AssertionError("unreachable: target_tenor_years bounded by the clamp checks above")


@dataclass(frozen=True)
class ModelImpliedPrice:
    dirty_price: Decimal
    accrued_interest: Decimal
    clean_price: Decimal


def model_implied_price(
    *,
    coupon_per_100: Decimal,
    maturity_date: dt.date,
    settlement_date: dt.date,
    curve: list[CurvePoint],
) -> ModelImpliedPrice:
    """Cum-dividend only (no ex-dividend handling) — a documented
    simplification appropriate for an already-estimated MODEL_IMPLIED
    value; a settlement-grade price would need that refinement, this
    doesn't claim to be one.
    """
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        timeline = timeline_for_settlement(
            maturity_date=maturity_date, settlement_date=settlement_date
        )
        coupon_payment = coupon_per_100 / COUPONS_PER_YEAR

        r = (timeline.next_quasi_coupon_date - settlement_date).days
        s = (
            timeline.next_quasi_coupon_date - timeline.previous_quasi_coupon_date
        ).days
        r_over_s = Decimal(r) / Decimal(s)

        dirty_price = Decimal(0)
        for j, cash_flow_date in enumerate(timeline.remaining_quasi_coupon_dates):
            amount = coupon_payment
            if cash_flow_date == maturity_date:
                amount += 100

            periods_elapsed = r_over_s + j
            tenor_years = periods_elapsed / COUPONS_PER_YEAR
            rate_pct = interpolate_curve(curve, tenor_years)
            discount_factor = (1 + rate_pct / 100 / COUPONS_PER_YEAR) ** (-periods_elapsed)
            dirty_price += amount * discount_factor

        accrued = accrued_interest(
            next_cash_flow=coupon_payment,
            days_since_previous_quasi_coupon=s - r,
            days_in_quasi_coupon_period=s,
            settled_on_or_before_ex_dividend=True,
        )

        return ModelImpliedPrice(
            dirty_price=dirty_price,
            accrued_interest=accrued,
            clean_price=dirty_price - accrued,
        )
