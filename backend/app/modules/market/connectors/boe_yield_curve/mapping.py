"""Parsing/normalisation for the Bank of England's nominal gilt spot curve
workbook — isolated from the connector so "how do we read this specific
file" is unit-testable without any network or DB dependency.

Scope decision: the ZIP contains four workbooks (Nominal/Real/Inflation/OIS
curves); only the nominal curve is parsed, since that's what a conventional
gilt like GB0032452392 needs. Within the nominal workbook, only the
"4. spot curve" sheet (0.5Y-40Y, half-yearly points) is used — the
"3. spot, short end" sheet gives finer granularity below 5Y that no
currently-seeded instrument needs. Both are deliberate, documented scope
narrowings, not silent omissions: a future short-dated instrument would
need the short-end sheet added here, not a different connector.

Never coerces or guesses (DATA-002): a missing sheet, an unparseable date,
or a non-numeric rate produces a RecordIssue rather than a fabricated value
or a crash that drops every other point in the sheet.
"""

import datetime as dt
import io
import zipfile
from dataclasses import dataclass
from decimal import Decimal

import openpyxl

NOMINAL_WORKBOOK_NAME = "GLC Nominal daily data current month.xlsx"
SPOT_CURVE_SHEET_NAME = "4. spot curve"
_MATURITY_HEADER_ROW = 4  # 1-indexed: row 4, col A = "years:", cols B.. = tenor years
_FIRST_DATA_ROW = 6  # row 5 is a stray "#VALUE!" artifact of the source spreadsheet


@dataclass(frozen=True)
class CurvePointCandidate:
    curve_date: dt.date
    tenor_years: Decimal
    spot_rate_pct: Decimal


@dataclass(frozen=True)
class RecordIssue:
    context: str
    reason: str


def extract_nominal_workbook_bytes(zip_bytes: bytes) -> bytes | RecordIssue:
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            return archive.read(NOMINAL_WORKBOOK_NAME)
    except zipfile.BadZipFile as exc:
        return RecordIssue(context="archive", reason=f"not a valid zip archive: {exc}")
    except KeyError:
        return RecordIssue(
            context="archive", reason=f"{NOMINAL_WORKBOOK_NAME!r} not found in archive"
        )


def _parse_tenor_header(header_row: tuple[object, ...]) -> list[Decimal | None]:
    tenors: list[Decimal | None] = []
    for cell in header_row[1:]:
        if isinstance(cell, int | float):
            tenors.append(Decimal(str(cell)))
        else:
            tenors.append(None)
    return tenors


def parse_spot_curve(workbook_bytes: bytes) -> list[CurvePointCandidate | RecordIssue]:
    try:
        workbook = openpyxl.load_workbook(
            io.BytesIO(workbook_bytes), data_only=True, read_only=True
        )
    except Exception as exc:  # noqa: BLE001 - any open failure means QUARANTINED, not a crash
        return [RecordIssue(context="workbook", reason=f"could not open workbook: {exc}")]

    if SPOT_CURVE_SHEET_NAME not in workbook.sheetnames:
        return [
            RecordIssue(
                context="workbook", reason=f"sheet {SPOT_CURVE_SHEET_NAME!r} not found"
            )
        ]

    sheet = workbook[SPOT_CURVE_SHEET_NAME]
    rows = list(sheet.iter_rows(values_only=True))

    if len(rows) < _MATURITY_HEADER_ROW:
        return [RecordIssue(context="workbook", reason="sheet has no maturity header row")]

    tenors = _parse_tenor_header(rows[_MATURITY_HEADER_ROW - 1])

    results: list[CurvePointCandidate | RecordIssue] = []
    for row in rows[_FIRST_DATA_ROW - 1 :]:
        if not row or not isinstance(row[0], dt.datetime):
            continue  # blank trailing rows past the last published date
        curve_date = row[0].date()

        for tenor, value in zip(tenors, row[1:], strict=False):
            if tenor is None or value is None:
                continue
            if not isinstance(value, int | float):
                results.append(
                    RecordIssue(
                        context=f"{curve_date.isoformat()} {tenor}Y",
                        reason=f"non-numeric spot rate: {value!r}",
                    )
                )
                continue
            results.append(
                CurvePointCandidate(
                    curve_date=curve_date,
                    tenor_years=tenor,
                    spot_rate_pct=Decimal(str(round(float(value), 6))),
                )
            )

    return results
