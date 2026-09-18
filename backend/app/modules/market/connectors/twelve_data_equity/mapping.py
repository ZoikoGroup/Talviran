"""Parsing/normalisation for Twelve Data's /time_series response — isolated
from the connector so "how do we read this specific shape" is
unit-testable without any network dependency.

Verified live (2026-09-18) against Twelve Data's real API, via their
public "demo" key (the only symbol family it serves is a small US
large-cap whitelist, e.g. AAPL): a successful response is

    {"meta": {"symbol": "AAPL", "currency": "USD", "exchange": "NASDAQ", ...},
     "values": [{"datetime": "2026-09-17", "open": "334.75500",
                 "high": "338.34000", "low": "330.19370", "close": "337",
                 "volume": "36423997"}, ...],
     "status": "ok"}

and Twelve Data's error envelope (confirmed live via an auth-error
response, which genuinely uses this shape) is

    {"code": 401, "message": "...", "status": "error"}

Per Twelve Data's own public documentation this same code/message/status
shape is also used for symbol-level errors (e.g. an unknown symbol),
sometimes returned with HTTP 200 rather than a 4xx — this is why
`status == "error"` is checked in the BODY here regardless of HTTP status.
The NSE-specific success shape (an actual NSE-listed symbol's real
response) is NOT independently confirmed — the demo key doesn't serve
NSE symbols and a real key wasn't available while building this — so this
parser is written against Twelve Data's own documented field names, not
an invented shape, and should be checked against one real NSE response
the first time a real key is available.

Never coerces or guesses (DATA-002): an error-status response, a missing
`values` array, or a row with an unparseable field produces a RecordIssue
rather than a fabricated value or a crash that drops every other row.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class EquityEodPriceCandidate:
    symbol: str
    exchange: str
    trade_date: dt.date
    close_price: Decimal
    currency_code: str


@dataclass(frozen=True)
class RecordIssue:
    raw_datetime: str | None
    reason: str


def parse_time_series(
    payload: Any, *, symbol: str, exchange: str
) -> list["EquityEodPriceCandidate | RecordIssue"]:
    if not isinstance(payload, dict):
        return [
            RecordIssue(
                raw_datetime=None,
                reason=f"expected a JSON object, got {type(payload).__name__}",
            )
        ]

    if payload.get("status") == "error":
        return [
            RecordIssue(
                raw_datetime=None,
                reason=f"Twelve Data error {payload.get('code')!r}: {payload.get('message')!r}",
            )
        ]

    meta = payload.get("meta")
    currency_code = meta.get("currency") if isinstance(meta, dict) else None
    if not currency_code:
        return [RecordIssue(raw_datetime=None, reason="missing meta.currency in response")]

    values = payload.get("values")
    if not isinstance(values, list):
        return [
            RecordIssue(raw_datetime=None, reason="missing or non-array 'values' in response")
        ]

    results: list[EquityEodPriceCandidate | RecordIssue] = []
    for row in values:
        if not isinstance(row, dict):
            results.append(
                RecordIssue(
                    raw_datetime=None, reason=f"expected an object row, got {type(row).__name__}"
                )
            )
            continue

        raw_datetime = row.get("datetime")
        if not raw_datetime:
            results.append(RecordIssue(raw_datetime=None, reason="missing 'datetime' field"))
            continue
        try:
            trade_date = dt.date.fromisoformat(str(raw_datetime)[:10])
        except ValueError:
            results.append(
                RecordIssue(
                    raw_datetime=str(raw_datetime),
                    reason=f"unparseable datetime: {raw_datetime!r}",
                )
            )
            continue

        raw_close = row.get("close")
        if raw_close is None:
            results.append(
                RecordIssue(raw_datetime=str(raw_datetime), reason="missing 'close' field")
            )
            continue
        try:
            close_price = Decimal(str(raw_close))
        except InvalidOperation:
            results.append(
                RecordIssue(
                    raw_datetime=str(raw_datetime),
                    reason=f"unparseable close price: {raw_close!r}",
                )
            )
            continue
        if close_price <= 0:
            results.append(
                RecordIssue(
                    raw_datetime=str(raw_datetime),
                    reason=f"non-positive close price: {close_price}",
                )
            )
            continue

        results.append(
            EquityEodPriceCandidate(
                symbol=symbol,
                exchange=exchange,
                trade_date=trade_date,
                close_price=close_price,
                currency_code=str(currency_code).upper(),
            )
        )

    return results
