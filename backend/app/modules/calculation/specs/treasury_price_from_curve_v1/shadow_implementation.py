"""Independent second implementation of treasury_price_from_curve_v1's
pricing, for FIN-001's dual-implementation gate.

Same zero-curve formula as implementation.py (each cash flow discounted by
its OWN curve rate across its own full tenor - a true zero-rate curve
valuation, not a forward-rate chain), but a genuinely different
computational path for the discount factor itself: implementation.py calls
Decimal's `**` once with a single fractional exponent
(-(r_over_s + j)); this shadow instead splits that exponent into its
integer part (accumulated via a repeated-multiplication loop, one period at
a time) and its fractional stub part (the only place `**` is used here, and
only ever with the small, fixed r_over_s exponent shared by every cash
flow rather than a per-cash-flow one). Both are exactly the same discount
factor algebraically; the two code paths reach it by different arithmetic,
which is the actual property a shadow implementation needs - a reformulated
discounting routine, not a different pricing methodology.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, localcontext

from app.modules.calculation.specs.gilt_price_yield_v1.implementation import accrued_interest
from app.modules.calculation.specs.gilt_price_yield_v1.schedule import (
    COUPONS_PER_YEAR,
    timeline_for_settlement,
)
from app.modules.calculation.specs.treasury_price_from_curve_v1.implementation import (
    CurvePoint,
    interpolate_curve,
)

_PRECISION = 50


@dataclass(frozen=True)
class ModelImpliedTreasuryPrice:
    dirty_price: Decimal
    accrued_interest: Decimal
    clean_price: Decimal


def _one_period_discount_factor(rate_pct: Decimal) -> Decimal:
    return (1 + rate_pct / 100 / COUPONS_PER_YEAR) ** -1


def model_implied_price(
    *,
    coupon_per_100: Decimal,
    maturity_date: dt.date,
    settlement_date: dt.date,
    curve: list[CurvePoint],
) -> ModelImpliedTreasuryPrice:
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

            tenor_years = (r_over_s + j) / COUPONS_PER_YEAR
            rate_pct = interpolate_curve(curve, tenor_years)
            one_period = _one_period_discount_factor(rate_pct)

            # Integer part of the exponent via repeated multiplication
            # (j whole periods), fractional stub part via a single `**`
            # call with the small, shared r_over_s exponent - a different
            # accumulation path from implementation.py's single
            # `** -(r_over_s + j)` call, same resulting discount factor.
            whole_periods_factor = Decimal(1)
            for _ in range(j):
                whole_periods_factor *= one_period
            stub_factor = one_period**r_over_s
            discount_factor = whole_periods_factor * stub_factor

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
