"""Unit tests for the Frankfurter FX parser, against real fixtures
(tests/fixtures/frankfurter_*.json, captured 2026-09-18 from Frankfurter's
live, public, unauthenticated v2 /rates endpoint) — proof the parser
handles the real response shape, not an invented one.
"""

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

from app.modules.market.connectors.frankfurter_fx.mapping import (
    FxRateCandidate,
    RecordIssue,
    parse_rates,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _load(name: str) -> object:
    return json.loads((FIXTURES_DIR / name).read_bytes())


def test_parses_single_pair_from_real_fixture() -> None:
    candidates = parse_rates(_load("frankfurter_gbp_inr.json"))
    assert candidates == [
        FxRateCandidate(
            base_currency="GBP", quote_currency="INR", rate=Decimal("128.76"),
            as_of=dt.date(2026, 9, 17),
        )
    ]


def test_parses_multi_quote_batch_with_independent_dates() -> None:
    candidates = parse_rates(_load("frankfurter_usd_gbp_inr.json"))
    assert candidates == [
        FxRateCandidate(
            base_currency="USD", quote_currency="GBP", rate=Decimal("0.74482"),
            as_of=dt.date(2026, 9, 18),
        ),
        FxRateCandidate(
            base_currency="USD", quote_currency="INR", rate=Decimal("95.91"),
            as_of=dt.date(2026, 9, 17),
        ),
    ]


def test_non_list_payload_is_a_record_issue_not_a_crash() -> None:
    result = parse_rates({"status": 422, "message": "invalid currency: ZZZ"})
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "expected a JSON array" in result[0].reason


def test_missing_field_is_a_record_issue() -> None:
    result = parse_rates([{"date": "2026-09-17", "base": "GBP", "quote": "INR"}])
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "rate" in result[0].reason


def test_non_numeric_rate_is_a_record_issue_not_a_guess() -> None:
    result = parse_rates(
        [{"date": "2026-09-17", "base": "GBP", "quote": "INR", "rate": "n/a"}]
    )
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert result[0].raw_quote_currency == "INR"
    assert "non-numeric rate" in result[0].reason


def test_non_positive_rate_is_a_record_issue() -> None:
    result = parse_rates(
        [{"date": "2026-09-17", "base": "GBP", "quote": "INR", "rate": 0}]
    )
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "non-positive rate" in result[0].reason


def test_unparseable_date_is_a_record_issue() -> None:
    result = parse_rates(
        [{"date": "not-a-date", "base": "GBP", "quote": "INR", "rate": 128.76}]
    )
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "unparseable date" in result[0].reason


def test_one_bad_record_does_not_drop_the_others_in_the_batch() -> None:
    result = parse_rates(
        [
            {"date": "2026-09-17", "base": "USD", "quote": "GBP", "rate": 0.74},
            {"date": "2026-09-17", "base": "USD", "quote": "ZZZ", "rate": "bad"},
        ]
    )
    assert len(result) == 2
    assert isinstance(result[0], FxRateCandidate)
    assert isinstance(result[1], RecordIssue)
