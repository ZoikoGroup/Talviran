"""Unit tests for the BoE yield curve parser, against the real fixture
(tests/fixtures/boe_yield_curve_latest.zip, captured 2026-09-15 from the
Bank of England's live, public, unauthenticated download) — proof the
parser handles the real file, not an invented shape.
"""

import datetime as dt
from decimal import Decimal
from pathlib import Path

from app.modules.market.connectors.boe_yield_curve.mapping import (
    CurvePointCandidate,
    RecordIssue,
    extract_nominal_workbook_bytes,
    parse_spot_curve,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "boe_yield_curve_latest.zip"
)


def test_extract_nominal_workbook_from_real_zip() -> None:
    zip_bytes = FIXTURE_PATH.read_bytes()
    result = extract_nominal_workbook_bytes(zip_bytes)
    assert not isinstance(result, RecordIssue)
    assert result[:2] == b"PK"  # xlsx is itself a zip


def test_extract_nominal_workbook_rejects_non_zip_bytes() -> None:
    result = extract_nominal_workbook_bytes(b"not a zip file")
    assert isinstance(result, RecordIssue)
    assert "not a valid zip archive" in result.reason


def test_parse_spot_curve_from_real_fixture() -> None:
    zip_bytes = FIXTURE_PATH.read_bytes()
    workbook_bytes = extract_nominal_workbook_bytes(zip_bytes)
    assert not isinstance(workbook_bytes, RecordIssue)

    candidates = parse_spot_curve(workbook_bytes)
    points = [c for c in candidates if isinstance(c, CurvePointCandidate)]
    issues = [c for c in candidates if isinstance(c, RecordIssue)]

    assert issues == [], f"unexpected parse issues: {issues}"
    assert len(points) > 0

    # Real, known point from the fixture: 2026-09-01, 10Y tenor.
    ten_year_sept1 = next(
        p
        for p in points
        if p.curve_date == dt.date(2026, 9, 1) and p.tenor_years == Decimal("10")
    )
    assert ten_year_sept1.spot_rate_pct == Decimal("5.206769")

    # Every published tenor should be a positive half-year increment up to 40.
    tenors = {p.tenor_years for p in points}
    assert Decimal("0.5") in tenors
    assert Decimal("40") in tenors
    assert all(t > 0 for t in tenors)


def test_parse_spot_curve_missing_sheet_produces_issue() -> None:
    import io

    import openpyxl

    workbook = openpyxl.Workbook()
    buffer = io.BytesIO()
    workbook.save(buffer)

    result = parse_spot_curve(buffer.getvalue())
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "not found" in result[0].reason
