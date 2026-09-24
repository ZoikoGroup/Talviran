"""Unit tests for the BoE GBP/USD spot-rate CSV parsing. The fixture is a
subset of rows captured verbatim from a live export on 2026-09-24 (see
boe_fx/client.py's docstring) - real dates, real published rates.
"""

import datetime as dt
from decimal import Decimal
from pathlib import Path

from app.modules.market.connectors.boe_fx.mapping import parse_rows
from app.modules.market.connectors.frankfurter_fx.mapping import FxRateCandidate, RecordIssue

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "boe_fx_gbp_usd_daily.csv"


def test_parses_every_row_from_the_real_captured_fixture() -> None:
    text = FIXTURE_PATH.read_text(encoding="utf-8-sig")
    results = parse_rows(text)
    assert len(results) == 5
    assert all(isinstance(r, FxRateCandidate) for r in results)


def test_each_row_maps_to_gbp_base_usd_quote() -> None:
    text = FIXTURE_PATH.read_text(encoding="utf-8-sig")
    results = parse_rows(text)
    first = results[0]
    assert isinstance(first, FxRateCandidate)
    assert first.base_currency == "GBP"
    assert first.quote_currency == "USD"
    assert first.as_of == dt.date(2026, 9, 1)
    assert first.rate == Decimal("1.3538")


def test_most_recent_row_parses_correctly() -> None:
    text = FIXTURE_PATH.read_text(encoding="utf-8-sig")
    results = parse_rows(text)
    last = results[-1]
    assert isinstance(last, FxRateCandidate)
    assert last.as_of == dt.date(2026, 9, 22)
    assert last.rate == Decimal("1.3348")


def test_unparseable_date_is_a_record_issue_not_a_crash() -> None:
    text = "DATE,XUDLUSS\nnot-a-date,1.35\n"
    results = parse_rows(text)
    assert len(results) == 1
    assert isinstance(results[0], RecordIssue)
    assert "date" in results[0].reason


def test_unparseable_rate_is_a_record_issue_not_a_crash() -> None:
    text = "DATE,XUDLUSS\n01 Sep 2026,n/a\n"
    results = parse_rows(text)
    assert len(results) == 1
    assert isinstance(results[0], RecordIssue)
    assert "rate" in results[0].reason


def test_wrong_columns_is_a_single_record_issue_not_a_crash() -> None:
    text = "DATE,SOME_OTHER_SERIES\n01 Sep 2026,1.35\n"
    results = parse_rows(text)
    assert len(results) == 1
    assert isinstance(results[0], RecordIssue)
    assert "expected columns" in results[0].reason
