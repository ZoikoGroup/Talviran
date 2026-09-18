"""Parsing/normalisation for Frankfurter's v2 /rates response — isolated
from the connector so "how do we read this specific shape" is
unit-testable without any network dependency.

Verified live against the real API (2026-09-18): a successful response is
a JSON array of per-quote-currency records, e.g.

    [{"date": "2026-09-18", "base": "USD", "quote": "GBP", "rate": 0.7448},
     {"date": "2026-09-17", "base": "USD", "quote": "INR", "rate": 95.91}]

Each record carries its OWN date, and these can genuinely differ between
quote currencies in the same batch (one quote currency's source can be a
day stale relative to another's, in the same response) — so a candidate's
as_of always comes from its own record, never from a shared "the whole
response is dated X" assumption.

Never coerces or guesses (DATA-002): a non-list payload, a record missing
a required field, or a non-positive/non-numeric rate produces a
RecordIssue for that one record rather than a fabricated value or a crash
that drops every other record in the batch.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

REQUIRED_FIELDS = ("date", "base", "quote", "rate")


@dataclass(frozen=True)
class FxRateCandidate:
    base_currency: str
    quote_currency: str
    rate: Decimal
    as_of: dt.date


@dataclass(frozen=True)
class RecordIssue:
    raw_quote_currency: str | None
    reason: str


def _parse_record(record: dict[str, Any]) -> "FxRateCandidate | RecordIssue":
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        return RecordIssue(
            raw_quote_currency=record.get("quote"),
            reason=f"missing required field(s): {', '.join(missing)}",
        )

    raw_rate = record["rate"]
    if not isinstance(raw_rate, int | float):
        return RecordIssue(
            raw_quote_currency=record.get("quote"), reason=f"non-numeric rate: {raw_rate!r}"
        )
    try:
        rate = Decimal(str(raw_rate))
    except InvalidOperation:
        return RecordIssue(
            raw_quote_currency=record.get("quote"), reason=f"unparseable rate: {raw_rate!r}"
        )
    if rate <= 0:
        return RecordIssue(
            raw_quote_currency=record.get("quote"), reason=f"non-positive rate: {rate}"
        )

    raw_date = record["date"]
    try:
        as_of = dt.date.fromisoformat(raw_date)
    except (TypeError, ValueError):
        return RecordIssue(
            raw_quote_currency=record.get("quote"), reason=f"unparseable date: {raw_date!r}"
        )

    return FxRateCandidate(
        base_currency=str(record["base"]).upper(),
        quote_currency=str(record["quote"]).upper(),
        rate=rate,
        as_of=as_of,
    )


def parse_rates(payload: Any) -> list["FxRateCandidate | RecordIssue"]:
    if not isinstance(payload, list):
        return [
            RecordIssue(
                raw_quote_currency=None,
                reason=f"expected a JSON array, got {type(payload).__name__}",
            )
        ]

    results: list[FxRateCandidate | RecordIssue] = []
    for record in payload:
        if not isinstance(record, dict):
            results.append(
                RecordIssue(
                    raw_quote_currency=None,
                    reason=f"expected an object, got {type(record).__name__}",
                )
            )
            continue
        results.append(_parse_record(record))
    return results
