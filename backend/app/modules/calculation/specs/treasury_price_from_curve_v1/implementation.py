"""Model-implied US Treasury (Note/Bond) pricing from the Treasury par
yield curve (app/modules/market/connectors/treasury_yield_curve/) — for
when no real per-security market price exists at all. Unlike gilts, there
is currently no per-security Treasury price source of any kind (see
scripts/onboard_all_treasury_securities.py's own docstring) - this spec's
output is the ONLY priced view of a Treasury Note/Bond this platform can
currently produce. Every result MUST be tagged BASIS_MODEL_IMPLIED
(calculation.models) and must never be written to, or displayed as, an
observed market fact - same boundary as gilt_price_from_curve_v1 and the
memory note "talvrin-model-implied-vs-market-price".

Method: discount the security's own real cash flows (from its
FiSovereignTerms, via the maturity-anchored quasi-coupon schedule) using
the Treasury par-yield curve, linearly interpolated at each cash flow's own
time-to-maturity - the same standard zero-curve discounted-cashflow
valuation gilt_price_from_curve_v1 performs, not a single-YTM
approximation.

Deliberately reuses gilt_price_yield_v1.schedule's quasi-coupon-date
stepping and gilt_price_yield_v1.implementation's accrued-interest formula
directly, rather than forking a parallel copy: both are the standard
semi-annual actual/actual government-bond convention (r/s stub + integer
periods, coupons_per_year=2) that UK gilts and US Treasury Notes/Bonds
share mechanically - the modules are jurisdiction-neutral bond-schedule
arithmetic, not UK-specific despite living under the gilt_price_yield_v1
package (gilt_holding_period_return_v1 already established this same reuse
precedent for the same reason). The *label* given to the day-count
convention on a Treasury's own FiSovereignTerms row stays "ACT_ACT_TREASURY"
(onboard_all_treasury_securities.py), independent of which shared utility
computed the schedule - this spec computes a schedule, it doesn't assert a
day-count-convention name.

Scope: Notes and Bonds only (both fixed semi-annual coupon) - TIPS are
excluded from this spec for the same reason UK index-linked gilts are
excluded from gilt_price_from_curve_v1: inflation-indexed principal needs
its own accrual/uplift methodology this spec doesn't implement. A TIPS
instrument simply has no priced calculation yet, same "omit, never invent"
posture as everywhere else in this codebase.
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
    par_yield_pct: Decimal


def interpolate_curve(curve: list[CurvePoint], target_tenor_years: Decimal) -> Decimal:
    """Linear interpolation between the two nearest published tenor points.
    A target outside the published range clamps to the nearest endpoint
    rather than extrapolating - same DATA-002 "never silently guess beyond
    the published domain" reasoning as gilt_price_from_curve_v1's own
    interpolate_curve.
    """
    if not curve:
        raise ValueError("curve must have at least one point")

    ordered = sorted(curve, key=lambda p: p.tenor_years)
    if target_tenor_years <= ordered[0].tenor_years:
        return ordered[0].par_yield_pct
    if target_tenor_years >= ordered[-1].tenor_years:
        return ordered[-1].par_yield_pct

    for lower, upper in zip(ordered, ordered[1:], strict=False):
        if lower.tenor_years <= target_tenor_years <= upper.tenor_years:
            span = upper.tenor_years - lower.tenor_years
            weight = (target_tenor_years - lower.tenor_years) / span
            return lower.par_yield_pct + weight * (upper.par_yield_pct - lower.par_yield_pct)

    raise AssertionError("unreachable: target_tenor_years bounded by the clamp checks above")


@dataclass(frozen=True)
class ModelImpliedTreasuryPrice:
    dirty_price: Decimal
    accrued_interest: Decimal
    clean_price: Decimal


def model_implied_price(
    *,
    coupon_per_100: Decimal,
    maturity_date: dt.date,
    settlement_date: dt.date,
    curve: list[CurvePoint],
) -> ModelImpliedTreasuryPrice:
    """Cum-dividend only (no settlement-day edge-case handling) - a
    documented simplification appropriate for an already-estimated
    MODEL_IMPLIED value, same as gilt_price_from_curve_v1's own.
    """
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        timeline = timeline_for_settlement(
            maturity_date=maturity_date, settlement_date=settlement_date
        )
        coupon_payment = coupon_per_100 / COUPONS_PER_YEAR

        r = (timeline.next_quasi_coupon_date - settlement_date).days
        s = (timeline.next_quasi_coupon_date - timeline.previous_quasi_coupon_date).days
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

        return ModelImpliedTreasuryPrice(
            dirty_price=dirty_price,
            accrued_interest=accrued,
            clean_price=dirty_price - accrued,
        )
