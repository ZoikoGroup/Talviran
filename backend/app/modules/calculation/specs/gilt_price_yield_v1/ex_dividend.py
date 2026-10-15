"""UK gilt ex-dividend period determination, from real calendar dates.

DMO's own rule (confirmed live against dmo.gov.uk/responsibilities/gilt-
market/about-gilts/, not assumed): a gilt enters its ex-dividend period
seven business days before the payment (coupon) date, and "entitlement is
based on settlement date, not trade date" - a trade settling on or after
that ex-dividend date forfeits the upcoming coupon.

"Business day" uses the England & Wales bank holiday calendar - gilts
settle via CREST in London, so England's calendar (not Scotland's or
Northern Ireland's, which differ on a few dates) is the correct one. Uses
the `holidays` PyPI package rather than a hand-maintained list, since a
hand-maintained UK bank-holiday list rots every year as new holidays are
gazetted (e.g. one-off additional bank holidays for coronations/jubilees).

This is deliberately a separate module from schedule.py: schedule.py's
`standard_inputs_from_dates` documents its own cum-dividend-only
assumption and is shared by two specs (gilt_price_yield_v1 and
gilt_price_from_curve_v1) that have not yet opted into ex-dividend
handling - adding a new runtime dependency (`holidays`) to that shared
module would force it on both, where only gilt_risk_metrics_v1's pricing
runner currently needs it.
"""

import datetime as dt

import holidays

#: DMO's own stated rule - see module docstring.
EX_DIVIDEND_BUSINESS_DAYS = 7

#: Lazily expands for whatever year is queried - no need to pre-specify a
#: year range, and no network call (the `holidays` package computes these
#: from fixed rules/known gazetted dates, it doesn't fetch anything).
_UK_HOLIDAYS = holidays.country_holidays("GB", subdiv="England")


def _is_business_day(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in _UK_HOLIDAYS


def _subtract_business_days(d: dt.date, n: int) -> dt.date:
    current = d
    remaining = n
    while remaining > 0:
        current -= dt.timedelta(days=1)
        if _is_business_day(current):
            remaining -= 1
    return current


def ex_dividend_date(payment_date: dt.date) -> dt.date:
    """The first date on which settlement no longer carries entitlement to
    `payment_date`'s coupon - DMO's own seven-business-days-before rule.
    """
    return _subtract_business_days(payment_date, EX_DIVIDEND_BUSINESS_DAYS)


def is_ex_dividend(*, settlement_date: dt.date, next_payment_date: dt.date) -> bool:
    """Entitlement is based on settlement date, not trade date (DMO) - a
    settlement ON the ex-dividend date itself is already ex-dividend
    (DMO: trades settling "on or after" that date forfeit the coupon).
    """
    return settlement_date >= ex_dividend_date(next_payment_date)
