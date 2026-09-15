"""Quasi-coupon date / day-count derivation for conventional gilts —
standard (non-first-period) settlements only, the same scope boundary as
implementation.py. Shared by gilt_price_yield_v1 (to derive r/s/n/d1/d2
from real dates instead of requiring a caller to precompute them) and
gilt_price_from_curve_v1 (to derive the cashflow schedule discounted
against the BoE curve) so both specs reason about a gilt's timeline
identically — this is also what makes the flat-curve consistency check
between them meaningful rather than comparing two independently-guessed
input sets.
"""

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    ConventionalGiltInputs,
)

COUPONS_PER_YEAR = 2  # f=2 for every current gilt, per DMO's own doc


def _shift_months(d: dt.date, months: int) -> dt.date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


@dataclass(frozen=True)
class GiltTimeline:
    previous_quasi_coupon_date: dt.date
    next_quasi_coupon_date: dt.date
    full_quasi_coupon_periods_remaining: int  # n
    remaining_quasi_coupon_dates: tuple[dt.date, ...]  # next_qc .. maturity, inclusive


def timeline_for_settlement(*, maturity_date: dt.date, settlement_date: dt.date) -> GiltTimeline:
    """DMO: quasi-coupon dates are defined by maturity's own semi-annual
    cycle, irrespective of whether cash flows occur on all of them. If
    settlement lands exactly ON a quasi-coupon date, that date is the
    PREVIOUS one (a fresh period has just started) and r=s for the period
    that follows — matching DMO's own stated convention and its worked
    "settlement on quasi-coupon date" examples exactly.
    """
    step = 12 // COUPONS_PER_YEAR
    upcoming: list[dt.date] = []
    current = maturity_date
    while current > settlement_date:
        upcoming.append(current)
        current = _shift_months(current, -step)
    upcoming.reverse()

    if not upcoming:
        raise ValueError("settlement_date must be strictly before maturity_date")

    next_qc = upcoming[0]
    previous_qc = _shift_months(next_qc, -step)
    return GiltTimeline(
        previous_quasi_coupon_date=previous_qc,
        next_quasi_coupon_date=next_qc,
        full_quasi_coupon_periods_remaining=len(upcoming) - 1,
        remaining_quasi_coupon_dates=tuple(upcoming),
    )


def standard_inputs_from_dates(
    *, coupon_per_100: Decimal, maturity_date: dt.date, settlement_date: dt.date
) -> ConventionalGiltInputs:
    """Standard case only: d1=d2=coupon/f exactly, and settlement is
    assumed cum-dividend (never ex-dividend) - a caller needing
    ex-dividend handling must adjust d1 to 0 itself; that's a settlement-
    convention decision this module deliberately doesn't make on its own.
    """
    timeline = timeline_for_settlement(maturity_date=maturity_date, settlement_date=settlement_date)
    r = (timeline.next_quasi_coupon_date - settlement_date).days
    s = (timeline.next_quasi_coupon_date - timeline.previous_quasi_coupon_date).days
    coupon_payment = coupon_per_100 / COUPONS_PER_YEAR

    return ConventionalGiltInputs(
        coupon_per_100=coupon_per_100,
        coupons_per_year=COUPONS_PER_YEAR,
        days_to_next_quasi_coupon=r,
        days_in_quasi_coupon_period=s,
        full_quasi_coupon_periods_remaining=timeline.full_quasi_coupon_periods_remaining,
        next_cash_flow=coupon_payment,
        next_but_one_cash_flow=coupon_payment,
    )
