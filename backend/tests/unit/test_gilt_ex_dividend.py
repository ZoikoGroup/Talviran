"""Proves ex_dividend.py's business-day arithmetic against manually
counted real calendar dates - not just that the loop runs, but that it
lands on the exact date DMO's "seven business days before the payment
date" rule implies, including across a UK bank holiday.
"""

import datetime as dt

from app.modules.calculation.specs.gilt_price_yield_v1.ex_dividend import (
    ex_dividend_date,
    is_ex_dividend,
)


def test_ex_dividend_date_skips_weekend_only() -> None:
    """Payment on a Monday with no UK bank holiday in the lookback window -
    just weekends to skip. Manually counted business days back from
    Mon 6 Jul 2026: Fri 3 Jul (1), Thu 2 Jul (2), Wed 1 Jul (3),
    Tue 30 Jun (4), Mon 29 Jun (5), Fri 26 Jun (6), Thu 25 Jun (7).
    """
    assert ex_dividend_date(dt.date(2026, 7, 6)) == dt.date(2026, 6, 25)


def test_ex_dividend_date_skips_a_uk_bank_holiday() -> None:
    """31 August 2026 is the Summer bank holiday (England) - a business-day
    count that didn't account for it would land one day earlier than
    correct (25 Aug, not 26 Aug). Manually counted business days back from
    Mon 7 Sep 2026: Fri 4 Sep (1), Thu 3 Sep (2), Wed 2 Sep (3),
    Tue 1 Sep (4), [Mon 31 Aug is the bank holiday - skipped],
    Fri 28 Aug (5), Thu 27 Aug (6), Wed 26 Aug (7).
    """
    assert ex_dividend_date(dt.date(2026, 9, 7)) == dt.date(2026, 8, 26)


def test_settlement_before_ex_dividend_date_is_cum_dividend() -> None:
    next_payment = dt.date(2026, 9, 7)
    assert not is_ex_dividend(
        settlement_date=dt.date(2026, 8, 25), next_payment_date=next_payment
    )


def test_settlement_on_ex_dividend_date_is_ex_dividend() -> None:
    """DMO: entitlement is based on settlement date, not trade date - a
    settlement exactly ON the ex-dividend date is already ex-dividend.
    """
    next_payment = dt.date(2026, 9, 7)
    assert is_ex_dividend(settlement_date=dt.date(2026, 8, 26), next_payment_date=next_payment)


def test_settlement_after_ex_dividend_date_is_ex_dividend() -> None:
    next_payment = dt.date(2026, 9, 7)
    assert is_ex_dividend(settlement_date=dt.date(2026, 9, 1), next_payment_date=next_payment)


def test_settlement_well_before_ex_dividend_window_is_cum_dividend() -> None:
    next_payment = dt.date(2026, 9, 7)
    assert not is_ex_dividend(
        settlement_date=dt.date(2026, 6, 1), next_payment_date=next_payment
    )
