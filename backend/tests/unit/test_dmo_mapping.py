"""Unit tests for DMO gilt parsing — every coupon pattern below is a real
string pulled from the actual fixture (tests/fixtures/dmo_gilts_in_issue.xml,
captured from a live DMO browser session on 2026-09-10), not invented
examples — so this is proof the parser handles DMO's real data, including
its real quirks (a trailing space in "Conventional ", a stray space in
"1¼ % Treasury Gilt 2041").
"""

import datetime as dt
from decimal import Decimal

import pytest

from app.modules.market.connectors.dmo_gilts.mapping import (
    GILT_TYPE_CONVENTIONAL,
    GILT_TYPE_INDEX_LINKED,
    RecordIssue,
    classify_gilt_type,
    normalise_record,
    parse_coupon_rate,
)

REAL_COUPON_EXAMPLES: list[tuple[str, Decimal]] = [
    ("0 3/8% Treasury Gilt 2026", Decimal("0.375")),
    ("4 1/8% Treasury Gilt 2027", Decimal("4.125")),
    ("3¾% Treasury Gilt 2027", Decimal("3.75")),
    ("1¼% Treasury Gilt 2027", Decimal("1.25")),
    ("4¼% Treasury Gilt 2027", Decimal("4.25")),
    ("6% Treasury Stock 2028", Decimal("6")),
    ("0½% Treasury Gilt 2029", Decimal("0.5")),
    ("4¼% Treasury Stock 2036", Decimal("4.25")),  # the seed instrument
    ("1¼ % Treasury Gilt 2041", Decimal("1.25")),  # real stray-space quirk
    ("1% Treasury Gilt 2032", Decimal("1")),
    ("4 5/8% Treasury Gilt 2032", Decimal("4.625")),
    ("0 7/8% Green Gilt 2033", Decimal("0.875")),
    ("5¼% Treasury Gilt 2041", Decimal("5.25")),
    ("1 1/8% Treasury Gilt 2039", Decimal("1.125")),
    ("2½% Treasury Gilt 2065", Decimal("2.5")),
    ("5 3/8% Treasury Gilt 2056", Decimal("5.375")),
    ("0¼% Index-linked Treasury Gilt 2052", Decimal("0.25")),
    ("4 1/8% Index-linked Treasury Stock 2030", Decimal("4.125")),
]


@pytest.mark.parametrize("instrument_name,expected", REAL_COUPON_EXAMPLES)
def test_parse_coupon_rate_real_examples(instrument_name: str, expected: Decimal) -> None:
    assert parse_coupon_rate(instrument_name) == expected


def test_parse_coupon_rate_returns_none_for_unrecognised_format() -> None:
    assert parse_coupon_rate("Some Future Gilt With No Coupon Prefix") is None


@pytest.mark.parametrize(
    "instrument_type,expected",
    [
        ("Conventional ", GILT_TYPE_CONVENTIONAL),  # real trailing-space quirk
        ("Index-linked 3 months", GILT_TYPE_INDEX_LINKED),
        ("Index-linked 8 months", GILT_TYPE_INDEX_LINKED),
    ],
)
def test_classify_gilt_type(instrument_type: str, expected: str) -> None:
    assert classify_gilt_type(instrument_type) == expected


def test_normalise_record_happy_path_seed_instrument() -> None:
    # The real GB0032452392 record, verbatim from the fixture.
    attrs = {
        "CLOSE_OF_BUSINESS_DATE": "2026-09-10T00:00:00",
        "INSTRUMENT_TYPE": "Conventional ",
        "MATURITY_BRACKET": "Medium",
        "INSTRUMENT_NAME": "4¼% Treasury Stock 2036",
        "ISIN_CODE": "GB0032452392",
        "REDEMPTION_DATE": "2036-03-07T00:00:00",
        "FIRST_ISSUE_DATE": "2003-02-27T00:00:00",
        "DIVIDEND_DATES": "7 Mar/Sep",
        "CURRENT_EX_DIV_DATE": "2027-02-25T00:00:00",
        "TOTAL_AMOUNT_IN_ISSUE": "32424.93300000000100000000",
    }

    result = normalise_record(attrs)

    assert not isinstance(result, RecordIssue)
    assert result.isin == "GB0032452392"
    assert result.instrument_name == "4¼% Treasury Stock 2036"
    assert result.gilt_type == GILT_TYPE_CONVENTIONAL
    assert result.coupon_rate == Decimal("4.25")
    assert result.redemption_date == dt.date(2036, 3, 7)
    assert result.first_issue_date == dt.date(2003, 2, 27)
    assert result.dividend_dates == "7 Mar/Sep"


def test_normalise_record_flags_missing_required_attribute() -> None:
    attrs = {
        "CLOSE_OF_BUSINESS_DATE": "2026-09-10T00:00:00",
        "INSTRUMENT_TYPE": "Conventional ",
        "INSTRUMENT_NAME": "4¼% Treasury Stock 2036",
        "ISIN_CODE": "GB0032452392",
        # REDEMPTION_DATE missing
        "FIRST_ISSUE_DATE": "2003-02-27T00:00:00",
        "DIVIDEND_DATES": "7 Mar/Sep",
        "TOTAL_AMOUNT_IN_ISSUE": "32424.933",
    }

    result = normalise_record(attrs)

    assert isinstance(result, RecordIssue)
    assert result.raw_isin == "GB0032452392"
    assert "REDEMPTION_DATE" in result.reason


def test_normalise_record_flags_unparseable_date_without_crashing() -> None:
    attrs = {
        "CLOSE_OF_BUSINESS_DATE": "2026-09-10T00:00:00",
        "INSTRUMENT_TYPE": "Conventional ",
        "INSTRUMENT_NAME": "4¼% Treasury Stock 2036",
        "ISIN_CODE": "GB0032452392",
        "REDEMPTION_DATE": "not-a-date",
        "FIRST_ISSUE_DATE": "2003-02-27T00:00:00",
        "DIVIDEND_DATES": "7 Mar/Sep",
        "TOTAL_AMOUNT_IN_ISSUE": "32424.933",
    }

    result = normalise_record(attrs)

    assert isinstance(result, RecordIssue)
    assert result.raw_isin == "GB0032452392"
