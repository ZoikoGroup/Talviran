"""Parsing/normalisation for the Bank of England IADB's `DATE,XUDLUSS` CSV
export - reuses frankfurter_fx's FxRateCandidate/RecordIssue rather than
declaring near-identical duplicates, since the shape a caller needs
(base/quote/rate/as_of, or an honest per-row issue) is genuinely the same
regardless of which source produced it.

Verified live against the real export (2026-09-24):

    DATE,XUDLUSS
    01 Sep 2026,1.3538
    02 Sep 2026,1.3506
    ...

XUDLUSS is "US dollar into Sterling" - USD per 1 GBP - so every row maps to
base_currency="GBP", quote_currency="USD". The database only ever returns
rows for days it actually published a rate for (no blank/holiday rows
observed), so a row with an unparseable date or rate is a genuine anomaly,
not an expected gap - it becomes a RecordIssue for that one row, never a
guessed value or a crash that drops the rest of the file (DATA-002).
"""

import csv
import datetime as dt
import io
from decimal import Decimal, InvalidOperation

from app.modules.market.connectors.frankfurter_fx.mapping import FxRateCandidate, RecordIssue

REQUIRED_COLUMNS = ("DATE", "XUDLUSS")
BASE_CURRENCY = "GBP"
QUOTE_CURRENCY = "USD"


def _parse_date(raw: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(raw.strip(), "%d %b %Y").date()
    except ValueError:
        return None


def _parse_rate(raw: str) -> Decimal | None:
    try:
        rate = Decimal(raw.strip())
    except InvalidOperation:
        return None
    return rate if rate > 0 else None


def parse_rows(csv_text: str) -> list[FxRateCandidate | RecordIssue]:
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None or list(reader.fieldnames) != list(REQUIRED_COLUMNS):
        return [
            RecordIssue(
                raw_quote_currency=None,
                reason=f"expected columns {REQUIRED_COLUMNS}, got {reader.fieldnames}",
            )
        ]

    results: list[FxRateCandidate | RecordIssue] = []
    for row in reader:
        raw_date = row["DATE"]
        raw_rate = row["XUDLUSS"]
        as_of = _parse_date(raw_date)
        if as_of is None:
            results.append(
                RecordIssue(
                    raw_quote_currency=QUOTE_CURRENCY,
                    reason=f"unparseable date: {raw_date!r}",
                )
            )
            continue
        rate = _parse_rate(raw_rate)
        if rate is None:
            results.append(
                RecordIssue(
                    raw_quote_currency=QUOTE_CURRENCY,
                    reason=f"unparseable/non-positive rate: {raw_rate!r}",
                )
            )
            continue
        results.append(
            FxRateCandidate(
                base_currency=BASE_CURRENCY, quote_currency=QUOTE_CURRENCY, rate=rate, as_of=as_of
            )
        )
    return results
