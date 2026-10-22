"""Unit tests for the TreasuryDirect auctioned-securities parser, against
real fixtures (tests/fixtures/treasurydirect_auctioned_*.json, captured
2026-10-22 from treasurydirect.gov's live, public, unauthenticated feed)
— proof the parser handles the real feed, not an invented shape.
"""

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.modules.market.connectors.treasury_securities.mapping import (
    RecordIssue,
    TreasurySecurityCandidate,
    parse_auctioned_securities,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _load(name: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = json.loads((FIXTURES_DIR / name).read_text())
    return result


def test_parse_real_note_fixture() -> None:
    records = _load("treasurydirect_auctioned_note.json")
    candidates = parse_auctioned_securities(records, queried_type="Note")
    securities = [c for c in candidates if isinstance(c, TreasurySecurityCandidate)]
    issues = [c for c in candidates if isinstance(c, RecordIssue)]

    assert issues == [], f"unexpected parse issues: {issues}"
    assert len(securities) == len(records)

    first = next(
        c for c in securities if c.cusip == "91282CRF0" and c.security_term == "9-Year 10-Month"
    )
    assert first.security_type == "Note"
    assert first.coupon_rate == Decimal("4.625")
    assert first.issue_date == dt.date(2026, 10, 15)
    assert first.maturity_date == dt.date(2036, 8, 15)


def test_parse_real_bond_fixture() -> None:
    records = _load("treasurydirect_auctioned_bond.json")
    candidates = parse_auctioned_securities(records, queried_type="Bond")
    securities = [c for c in candidates if isinstance(c, TreasurySecurityCandidate)]

    assert len(securities) == len(records)
    first = next(c for c in securities if c.cusip == "912810UX4")
    assert first.security_type == "Bond"
    assert first.coupon_rate == Decimal("5.125")
    assert first.maturity_date == dt.date(2046, 8, 15)


def test_parse_real_tips_fixture_classified_by_flag_not_query_type() -> None:
    records = _load("treasurydirect_auctioned_tips.json")
    # Deliberately queried_type="Note" - proves classification comes from
    # the record's own inflationProtected flag, not an echo of the caller's
    # query parameter.
    candidates = parse_auctioned_securities(records, queried_type="Note")
    securities = [c for c in candidates if isinstance(c, TreasurySecurityCandidate)]

    assert len(securities) == 1
    tips = securities[0]
    assert tips.cusip == "91282CRE3"
    assert tips.security_type == "TIPS"
    assert tips.coupon_rate == Decimal("2.375")


def test_parse_real_frn_fixture_is_skipped_not_guessed() -> None:
    records = _load("treasurydirect_auctioned_frn.json")
    candidates = parse_auctioned_securities(records, queried_type="Note")
    securities = [c for c in candidates if isinstance(c, TreasurySecurityCandidate)]
    issues = [c for c in candidates if isinstance(c, RecordIssue)]

    assert securities == [], "a floating-rate note has no fixed coupon to store"
    assert len(issues) == len(records)
    assert all("floating-rate" in issue.reason for issue in issues)


def test_missing_cusip_is_a_record_issue() -> None:
    result = parse_auctioned_securities(
        [{"issueDate": "2026-01-01T00:00:00"}], queried_type="Note"
    )
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "missing cusip" in result[0].reason


def test_bill_like_record_with_no_interest_rate_is_a_record_issue() -> None:
    result = parse_auctioned_securities(
        [
            {
                "cusip": "912797XA0",
                "issueDate": "2026-10-27T00:00:00",
                "maturityDate": "2027-02-23T00:00:00",
                "interestRate": "",
            }
        ],
        queried_type="Bill",
    )
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "no interestRate" in result[0].reason


def test_unparseable_date_is_a_record_issue() -> None:
    result = parse_auctioned_securities(
        [
            {
                "cusip": "91282CRF0",
                "issueDate": "not-a-date",
                "maturityDate": "2036-08-15T00:00:00",
                "interestRate": "4.625",
            }
        ],
        queried_type="Note",
    )
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "unparseable" in result[0].reason
