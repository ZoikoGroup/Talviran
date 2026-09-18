"""Unit tests for the Twelve Data equity-price parser.

test_twelvedata_aapl_demo.json is real: captured 2026-09-18 from Twelve
Data's live, public "demo" key. The demo key only ever serves a small US
large-cap whitelist (AAPL and similar), never an NSE-listed symbol, so
there is no live-captured NSE response to test against yet — the NSE
cases below are hand-built to Twelve Data's own documented field shape
(same meta/values/status structure the real AAPL response shows), and
should be re-checked against one real NSE response the first time a real
API key is available (see mapping.py's module docstring).
"""

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

from app.modules.market.connectors.twelve_data_equity.mapping import (
    EquityEodPriceCandidate,
    RecordIssue,
    parse_time_series,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _load(name: str) -> object:
    return json.loads((FIXTURES_DIR / name).read_bytes())


def test_parses_real_demo_response() -> None:
    candidates = parse_time_series(
        _load("twelvedata_aapl_demo.json"), symbol="AAPL", exchange="NASDAQ"
    )
    assert candidates == [
        EquityEodPriceCandidate(
            symbol="AAPL", exchange="NASDAQ", trade_date=dt.date(2026, 9, 17),
            close_price=Decimal("337"), currency_code="USD",
        ),
        EquityEodPriceCandidate(
            symbol="AAPL", exchange="NASDAQ", trade_date=dt.date(2026, 9, 16),
            close_price=Decimal("332.41000"), currency_code="USD",
        ),
    ]


def test_parses_hand_built_nse_shaped_response() -> None:
    payload = {
        "meta": {
            "symbol": "TATAMOTORS", "interval": "1day", "currency": "INR",
            "exchange_timezone": "Asia/Kolkata", "exchange": "NSE",
            "mic_code": "XNSE", "type": "Common Stock",
        },
        "values": [
            {"datetime": "2026-09-17", "open": "690.00", "high": "698.50",
             "low": "685.10", "close": "695.25", "volume": "9876543"},
        ],
        "status": "ok",
    }
    candidates = parse_time_series(payload, symbol="TATAMOTORS", exchange="NSE")
    assert candidates == [
        EquityEodPriceCandidate(
            symbol="TATAMOTORS", exchange="NSE", trade_date=dt.date(2026, 9, 17),
            close_price=Decimal("695.25"), currency_code="INR",
        )
    ]


def test_error_status_is_a_record_issue_not_a_crash() -> None:
    # The real shape confirmed live via an auth-error response
    # (code/message/status) — Twelve Data documents the same envelope for
    # symbol-level errors too, sometimes via HTTP 200.
    payload = {"code": 400, "message": "**symbol** not found", "status": "error"}
    result = parse_time_series(payload, symbol="NOTREAL", exchange="NSE")
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "Twelve Data error" in result[0].reason


def test_missing_values_array_is_a_record_issue() -> None:
    payload = {"meta": {"currency": "INR"}, "status": "ok"}
    result = parse_time_series(payload, symbol="TATAMOTORS", exchange="NSE")
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "values" in result[0].reason


def test_missing_currency_is_a_record_issue() -> None:
    payload = {"meta": {}, "values": [], "status": "ok"}
    result = parse_time_series(payload, symbol="TATAMOTORS", exchange="NSE")
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "currency" in result[0].reason


def test_missing_close_field_is_a_record_issue_not_a_guess() -> None:
    payload = {
        "meta": {"currency": "INR"},
        "values": [{"datetime": "2026-09-17", "open": "690.00"}],
        "status": "ok",
    }
    result = parse_time_series(payload, symbol="TATAMOTORS", exchange="NSE")
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "close" in result[0].reason


def test_non_positive_close_is_a_record_issue() -> None:
    payload = {
        "meta": {"currency": "INR"},
        "values": [{"datetime": "2026-09-17", "close": "0"}],
        "status": "ok",
    }
    result = parse_time_series(payload, symbol="TATAMOTORS", exchange="NSE")
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "non-positive" in result[0].reason


def test_one_bad_row_does_not_drop_the_others() -> None:
    payload = {
        "meta": {"currency": "INR"},
        "values": [
            {"datetime": "2026-09-17", "close": "695.25"},
            {"datetime": "2026-09-16", "close": "not-a-number"},
        ],
        "status": "ok",
    }
    result = parse_time_series(payload, symbol="TATAMOTORS", exchange="NSE")
    assert len(result) == 2
    assert isinstance(result[0], EquityEodPriceCandidate)
    assert isinstance(result[1], RecordIssue)
