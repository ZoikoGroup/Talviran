"""Production implementation of a conventional gilt's holding-period
return between two dates — the standard textbook definition (e.g. Fabozzi,
"Bond Markets, Analysis, and Strategies"), re-derived here via plain
arithmetic rather than transcribed from memory. No DMO-published source
exists for this (the DMO's own pinned methodology document covers only
price/yield conversion, dividend calculation and accrued interest — same
scope gap gilt_risk_metrics_v1's own docstring already documents).

    HPR = (P1 - P0 + Income) / P0

where P0/P1 are DIRTY prices (dirty price already embeds accrued interest,
so dirty-to-dirty comparison never double-counts the accrued-interest
component at either boundary the way clean-to-clean would), and Income is
the sum of coupon cash actually PAID strictly between the two dates (not
accrued-but-unpaid interest, which dirty price already captures at each
boundary on its own).

Coupon payment dates are derived from the gilt's own quasi-coupon
timeline (gilt_price_yield_v1.schedule.timeline_for_settlement) — the
exact same schedule used to price the gilt itself, so holding-period
income is counted against the identical calendar, not a second,
independently-guessed one.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from app.modules.calculation.specs.gilt_price_yield_v1.schedule import (
    COUPONS_PER_YEAR,
    timeline_for_settlement,
)


@dataclass(frozen=True)
class HoldingPeriodInputs:
    coupon_per_100: Decimal
    maturity_date: dt.date
    start_date: dt.date
    start_dirty_price: Decimal
    end_date: dt.date
    end_dirty_price: Decimal


@dataclass(frozen=True)
class HoldingPeriodReturn:
    coupon_payments_received: int
    income_received: Decimal
    price_return: Decimal  # end_dirty_price - start_dirty_price
    total_return_amount: Decimal  # price_return + income_received
    holding_period_return_pct: Decimal


def coupon_payments_received_between(
    *, coupon_per_100: Decimal, maturity_date: dt.date, start_date: dt.date, end_date: dt.date
) -> int:
    """How many coupon payment dates fall strictly after start_date and on
    or before end_date — "strictly after" because a payment ON start_date
    itself is already reflected in start_date's own dirty price (zero
    accrued interest that morning), not income earned DURING this holding
    period; "on or before end_date" because a payment landing exactly on
    end_date has genuinely been received by the end of the period.
    """
    if end_date <= start_date:
        raise ValueError("end_date must be strictly after start_date")
    timeline = timeline_for_settlement(maturity_date=maturity_date, settlement_date=start_date)
    return sum(1 for d in timeline.remaining_quasi_coupon_dates if start_date < d <= end_date)


def compute_holding_period_return(inputs: HoldingPeriodInputs) -> HoldingPeriodReturn:
    payments = coupon_payments_received_between(
        coupon_per_100=inputs.coupon_per_100,
        maturity_date=inputs.maturity_date,
        start_date=inputs.start_date,
        end_date=inputs.end_date,
    )
    coupon_payment = inputs.coupon_per_100 / COUPONS_PER_YEAR
    income_received = coupon_payment * payments
    price_return = inputs.end_dirty_price - inputs.start_dirty_price
    total_return_amount = price_return + income_received
    holding_period_return_pct = (total_return_amount / inputs.start_dirty_price) * 100

    return HoldingPeriodReturn(
        coupon_payments_received=payments,
        income_received=income_received,
        price_return=price_return,
        total_return_amount=total_return_amount,
        holding_period_return_pct=holding_period_return_pct,
    )
