"""Unit tests for the US Treasury yield curve parser, against the real
fixture (tests/fixtures/treasury_yield_curve_2026.xml, captured 2026-10-22
from home.treasury.gov's live, public, unauthenticated feed) — proof the
parser handles the real feed, not an invented shape.
"""

import datetime as dt
from decimal import Decimal
from pathlib import Path

from app.modules.market.connectors.treasury_yield_curve.mapping import (
    CurvePointCandidate,
    RecordIssue,
    parse_yield_curve,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "treasury_yield_curve_2026.xml"
)


def test_parse_yield_curve_from_real_fixture() -> None:
    xml_bytes = FIXTURE_PATH.read_bytes()
    candidates = parse_yield_curve(xml_bytes)
    points = [c for c in candidates if isinstance(c, CurvePointCandidate)]
    issues = [c for c in candidates if isinstance(c, RecordIssue)]

    assert issues == [], f"unexpected parse issues: {issues}"
    assert len(points) > 0

    # Real, known point from the fixture: 2026-01-02, 10 Year tenor.
    ten_year_jan2 = next(
        p
        for p in points
        if p.curve_date == dt.date(2026, 1, 2) and p.tenor_field == "BC_10YEAR"
    )
    assert ten_year_jan2.par_yield_pct == Decimal("4.19")
    assert ten_year_jan2.tenor_label == "10 Year"

    # Every curve date in the fixture spans the full year through the
    # capture date - not just the first/last row.
    dates = {p.curve_date for p in points}
    assert dt.date(2026, 1, 2) in dates
    assert dt.date(2026, 10, 21) in dates

    # BC_30YEARDISPLAY is deliberately excluded (see mapping.py docstring).
    assert all(p.tenor_field != "BC_30YEARDISPLAY" for p in points)


def test_parse_yield_curve_rejects_malformed_xml() -> None:
    result = parse_yield_curve(b"not xml at all")
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "not well-formed XML" in result[0].reason


def test_parse_yield_curve_empty_feed_produces_no_candidates() -> None:
    empty_feed = (
        b'<?xml version="1.0" encoding="utf-8" standalone="yes" ?>'
        b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    )
    result = parse_yield_curve(empty_feed)
    assert result == []


def test_parse_yield_curve_non_numeric_yield_produces_issue() -> None:
    bad_entry = b"""<?xml version="1.0" encoding="utf-8" standalone="yes" ?>
<feed xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
      xmlns="http://www.w3.org/2005/Atom">
<entry>
<content type="application/xml">
<m:properties>
<d:NEW_DATE m:type="Edm.DateTime">2026-01-02T00:00:00</d:NEW_DATE>
<d:BC_10YEAR m:type="Edm.Double">N/A</d:BC_10YEAR>
</m:properties>
</content>
</entry>
</feed>"""
    result = parse_yield_curve(bad_entry)
    assert len(result) == 1
    assert isinstance(result[0], RecordIssue)
    assert "non-numeric par yield" in result[0].reason
