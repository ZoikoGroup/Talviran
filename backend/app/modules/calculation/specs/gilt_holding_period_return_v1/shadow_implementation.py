"""Shadow (validation-only) implementation of the holding-period return —
FIN-001's dual-implementation gate. Two independent departures from the
production path, not a restatement of it:

1. Coupon payment dates are derived by this module's OWN backward-stepping
   loop from maturity_date, never calling
   gilt_price_yield_v1.schedule.timeline_for_settlement — so a bug in that
   shared schedule logic (which production also depends on for pricing
   elsewhere) would not silently agree with itself here.
2. The return itself is computed as a ratio minus one
   ((end_dirty_price + income) / start_dirty_price - 1) rather than
   production's (total_return_amount / start_dirty_price), a different
   order of floating/decimal operations that would surface a rounding
   divergence the other form could mask.
"""

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from app.modules.calculation.specs.gilt_holding_period_return_v1.implementation import (
    HoldingPeriodInputs,
)

_COUPONS_PER_YEAR = 2
_MONTHS_PER_PERIOD = 12 // _COUPONS_PER_YEAR


def _step_back_one_period(d: dt.date) -> dt.date:
    month_index = d.month - 1 - _MONTHS_PER_PERIOD
    year = d.year + (month_index // 12)
    month = month_index % 12 + 1
    # Clamp the day independently of schedule.py's own _shift_months, using
    # the stdlib's own days-in-month table directly.
    day = min(d.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


@dataclass(frozen=True)
class HoldingPeriodReturn:
    coupon_payments_received: int
    income_received: Decimal
    price_return: Decimal
    total_return_amount: Decimal
    holding_period_return_pct: Decimal


def coupon_payments_received_between(
    *, maturity_date: dt.date, start_date: dt.date, end_date: dt.date
) -> int:
    if end_date <= start_date:
        raise ValueError("end_date must be strictly after start_date")

    count = 0
    current = maturity_date
    while current > start_date:
        if current <= end_date:
            count += 1
        current = _step_back_one_period(current)
    return count


def compute_holding_period_return(inputs: HoldingPeriodInputs) -> HoldingPeriodReturn:
    payments = coupon_payments_received_between(
        maturity_date=inputs.maturity_date, start_date=inputs.start_date, end_date=inputs.end_date
    )
    coupon_payment = inputs.coupon_per_100 / _COUPONS_PER_YEAR
    income_received = coupon_payment * payments
    price_return = inputs.end_dirty_price - inputs.start_dirty_price
    total_return_amount = price_return + income_received
    holding_period_return_pct = (
        (inputs.end_dirty_price + income_received) / inputs.start_dirty_price - 1
    ) * 100

    return HoldingPeriodReturn(
        coupon_payments_received=payments,
        income_received=income_received,
        price_return=price_return,
        total_return_amount=total_return_amount,
        holding_period_return_pct=holding_period_return_pct,
    )
