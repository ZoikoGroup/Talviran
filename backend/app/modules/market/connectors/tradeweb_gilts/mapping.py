"""Parsing/normalisation for Tradeweb's gilt closing-price export CSV -
isolated from the connector so "how do we read this specific CSV shape"
is unit-testable without any network/auth dependency, same convention as
dmo_gilts/mapping.py.

Never coerces or guesses (DATA-002): a row with no parseable clean price
or yield produces a RecordIssue for that one row, never a fabricated
value or a crash that drops every other row.

Real column header, confirmed live 2026-09-23 against the actual
export: "Gilt Name","Close of Business Date","ISIN","Type","Coupon",
"Maturity","Clean Price","Dirty Price","Yield","Mod Duration",
"Accrued Interest". The file covers more than UK conventional gilts
(Treasury Bills, other European sovereigns were present in the real
export) - this module parses every row generically; a caller decides
which rows are in scope (see scripts/ingest_tradeweb_gilt_prices.py's
GB-ISIN + Conventional-only filter, matching what
scripts.onboard_all_gilts already onboarded).
"""

import csv
import datetime as dt
import io
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

REQUIRED_COLUMNS = (
    "Gilt Name",
    "Close of Business Date",
    "ISIN",
    "Type",
    "Clean Price",
    "Yield",
)


@dataclass(frozen=True)
class TradewebPriceCandidate:
    isin: str
    instrument_name: str
    instrument_type: str
    close_of_business_date: dt.date
    clean_price: Decimal
    dirty_price: Decimal | None
    yield_pct: Decimal
    mod_duration: Decimal | None
    accrued_interest: Decimal | None


@dataclass(frozen=True)
class RecordIssue:
    raw_isin: str | None
    reason: str


def _parse_decimal_or_none(value: str | None) -> Decimal | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value.upper() == "N/A":
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _parse_date(value: str) -> dt.date:
    # Tradeweb's own format, confirmed live: "9/21/2026" (M/D/YYYY, no
    # leading zeros) - never assumed from docs, read off the real export.
    return dt.datetime.strptime(value.strip(), "%m/%d/%Y").date()


def parse_rows(csv_text: str) -> list[TradewebPriceCandidate | RecordIssue]:
    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = reader.fieldnames or []
    missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
    if missing:
        return [RecordIssue(raw_isin=None, reason=f"missing column(s): {missing}")]

    results: list[TradewebPriceCandidate | RecordIssue] = []
    for row in reader:
        isin = (row.get("ISIN") or "").strip()
        try:
            close_date = _parse_date(row["Close of Business Date"])
        except (KeyError, ValueError) as exc:
            results.append(RecordIssue(raw_isin=isin or None, reason=f"unparseable date: {exc}"))
            continue

        clean_price = _parse_decimal_or_none(row.get("Clean Price"))
        yield_pct = _parse_decimal_or_none(row.get("Yield"))
        if clean_price is None or yield_pct is None:
            results.append(
                RecordIssue(raw_isin=isin or None, reason="missing clean price or yield")
            )
            continue

        results.append(
            TradewebPriceCandidate(
                isin=isin,
                instrument_name=(row.get("Gilt Name") or "").strip(),
                instrument_type=(row.get("Type") or "").strip(),
                close_of_business_date=close_date,
                clean_price=clean_price,
                dirty_price=_parse_decimal_or_none(row.get("Dirty Price")),
                yield_pct=yield_pct,
                mod_duration=_parse_decimal_or_none(row.get("Mod Duration")),
                accrued_interest=_parse_decimal_or_none(row.get("Accrued Interest")),
            )
        )
    return results
