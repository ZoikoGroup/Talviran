"""Proves timeline_for_settlement/standard_inputs_from_dates reproduce the
real r/s/n values from DMO's own worked examples (yldconv.pdf) when driven
from actual calendar dates - not just that the closed-form formula is
right (that's golden/v1/corpus.json's job) but that deriving its inputs
from real dates is also right. Only the cum-dividend scenarios (1, 2, 4)
are usable here: scenario 3 in each bond settles ex-dividend, which this
module deliberately doesn't compute (see its own docstring).
"""

import datetime as dt
from decimal import Decimal

import pytest

from app.modules.calculation.specs.gilt_price_yield_v1.schedule import (
    standard_inputs_from_dates,
    timeline_for_settlement,
)

# (settlement, expected_previous_qc, expected_next_qc, expected_r, expected_s, expected_n)
_8PC_2015_MATURITY = dt.date(2015, 12, 7)
_8PC_2015_CASES = [
    (dt.date(1999, 5, 24), dt.date(1998, 12, 7), dt.date(1999, 6, 7), 14, 182, 33),
    (dt.date(1999, 5, 26), dt.date(1998, 12, 7), dt.date(1999, 6, 7), 12, 182, 33),
    (dt.date(1999, 6, 7), dt.date(1999, 6, 7), dt.date(1999, 12, 7), 183, 183, 32),
]

_675PC_2004_MATURITY = dt.date(2004, 11, 26)
_675PC_2004_CASES = [
    (dt.date(1999, 5, 10), dt.date(1998, 11, 26), dt.date(1999, 5, 26), 16, 181, 11),
    (dt.date(1999, 5, 17), dt.date(1998, 11, 26), dt.date(1999, 5, 26), 9, 181, 11),
    (dt.date(1999, 5, 26), dt.date(1999, 5, 26), dt.date(1999, 11, 26), 184, 184, 10),
]


@pytest.mark.parametrize(
    "settlement,expected_previous_qc,expected_next_qc,expected_r,expected_s,expected_n",
    _8PC_2015_CASES,
)
def test_8pc2015_timeline_matches_dmo_worked_example(
    settlement: dt.date, expected_previous_qc: dt.date, expected_next_qc: dt.date,
    expected_r: int, expected_s: int, expected_n: int,
) -> None:
    timeline = timeline_for_settlement(maturity_date=_8PC_2015_MATURITY, settlement_date=settlement)
    assert timeline.previous_quasi_coupon_date == expected_previous_qc
    assert timeline.next_quasi_coupon_date == expected_next_qc
    assert (timeline.next_quasi_coupon_date - settlement).days == expected_r
    assert (
        timeline.next_quasi_coupon_date - timeline.previous_quasi_coupon_date
    ).days == expected_s
    assert timeline.full_quasi_coupon_periods_remaining == expected_n


@pytest.mark.parametrize(
    "settlement,expected_previous_qc,expected_next_qc,expected_r,expected_s,expected_n",
    _675PC_2004_CASES,
)
def test_675pc2004_timeline_matches_dmo_worked_example(
    settlement: dt.date, expected_previous_qc: dt.date, expected_next_qc: dt.date,
    expected_r: int, expected_s: int, expected_n: int,
) -> None:
    timeline = timeline_for_settlement(
        maturity_date=_675PC_2004_MATURITY, settlement_date=settlement
    )
    assert timeline.previous_quasi_coupon_date == expected_previous_qc
    assert timeline.next_quasi_coupon_date == expected_next_qc
    assert (timeline.next_quasi_coupon_date - settlement).days == expected_r
    assert (
        timeline.next_quasi_coupon_date - timeline.previous_quasi_coupon_date
    ).days == expected_s
    assert timeline.full_quasi_coupon_periods_remaining == expected_n


def test_standard_inputs_from_dates_feeds_the_pricing_formula_correctly() -> None:
    from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
        dirty_price_from_yield,
    )

    inputs = standard_inputs_from_dates(
        coupon_per_100=Decimal("8"),
        maturity_date=_8PC_2015_MATURITY,
        settlement_date=dt.date(1999, 5, 24),
    )
    price = dirty_price_from_yield(inputs, Decimal("0.04445"))
    assert abs(price - Decimal("145.012268")) < Decimal("1E-6")


def test_settlement_on_or_after_maturity_is_rejected() -> None:
    with pytest.raises(ValueError, match="strictly before"):
        timeline_for_settlement(
            maturity_date=dt.date(2020, 1, 1), settlement_date=dt.date(2020, 1, 1)
        )
