"""Unit tests for Tradeweb gilt closing-price CSV parsing. The fixture's
first two data rows are real, captured verbatim from a live export on
2026-09-23 (a UK Treasury Bill and an Italian BTPS row, proving the file
covers more than just UK conventional gilts) - the third row (our own
seed gilt, GB0032452392) uses the real instrument's real coupon/maturity
but a constructed price, since our own live verification didn't happen
to capture that exact ISIN's row before deliberately stopping further
live calls to avoid the endpoint's apparent rate limit. The fourth row
is a real index-linked gilt with real "N/A" price/yield fields, proving
that case degrades to a RecordIssue rather than a crash or a guessed 0.
"""

import datetime as dt
from decimal import Decimal
from pathlib import Path

from app.modules.market.connectors.tradeweb_gilts.mapping import (
    RecordIssue,
    TradewebPriceCandidate,
    parse_rows,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "tradeweb_gilt_closing_prices.csv"
)


def test_parses_every_row_from_the_real_captured_fixture() -> None:
    text = FIXTURE_PATH.read_text(encoding="utf-8-sig")
    results = parse_rows(text)
    assert len(results) == 4


def test_a_uk_treasury_bill_row_parses_with_na_dirty_price_as_none() -> None:
    text = FIXTURE_PATH.read_text(encoding="utf-8-sig")
    results = parse_rows(text)
    bill = next(
        r for r in results
        if isinstance(r, TradewebPriceCandidate) and r.isin.startswith("GB00BSGQ")
    )
    assert bill.instrument_type == "Bills"
    assert bill.clean_price == Decimal("99.936984")
    assert bill.dirty_price is None  # real "N/A" in this column for bills
    assert bill.close_of_business_date == dt.date(2026, 9, 21)


def test_a_non_uk_sovereign_row_parses_too_not_filtered_here() -> None:
    """Filtering to GB-ISIN Conventional gilts is the ingestion SCRIPT's
    job (matching what's actually onboarded), not the mapping module's -
    parse_rows stays a generic, honest reader of whatever the file
    contains, same convention as dmo_gilts/mapping.py.
    """
    text = FIXTURE_PATH.read_text(encoding="utf-8-sig")
    results = parse_rows(text)
    btps = next(
        r for r in results
        if isinstance(r, TradewebPriceCandidate) and r.isin.startswith("IT")
    )
    assert btps.instrument_type == "Conventional"
    assert btps.yield_pct == Decimal("4.288992")


def test_our_seed_gilt_parses_with_real_clean_dirty_and_accrued() -> None:
    text = FIXTURE_PATH.read_text(encoding="utf-8-sig")
    results = parse_rows(text)
    seed = next(
        r for r in results
        if isinstance(r, TradewebPriceCandidate) and r.isin == "GB0032452392"
    )
    assert seed.clean_price == Decimal("93.410")
    assert seed.dirty_price == Decimal("93.512")
    assert seed.accrued_interest == Decimal("0.102")


def test_index_linked_row_with_na_price_and_yield_is_a_record_issue_not_a_crash() -> None:
    text = FIXTURE_PATH.read_text(encoding="utf-8-sig")
    results = parse_rows(text)
    issue = next(r for r in results if isinstance(r, RecordIssue))
    assert issue.raw_isin == "GB00BM8Z2V59"
    assert "clean price" in issue.reason or "yield" in issue.reason


def test_missing_required_column_is_a_single_record_issue_not_a_crash() -> None:
    header_only_missing_isin = (
        '"Gilt Name","Close of Business Date","Type","Clean Price","Yield"\n'
        '"Some Gilt","9/21/2026","Conventional","100.00","4.0"\n'
    )
    results = parse_rows(header_only_missing_isin)
    assert len(results) == 1
    assert isinstance(results[0], RecordIssue)
    assert "ISIN" in results[0].reason
