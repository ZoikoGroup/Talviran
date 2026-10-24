"""Parsing/normalisation for the US Treasury's daily par yield curve
ATOM/OData feed — isolated from the connector so "how do we read this
specific feed" is unit-testable without any network or DB dependency.

Identity decision: each candidate's tenor is keyed by the source's own XML
field name (e.g. "BC_10YEAR"), never a derived fractional-year Decimal
(1 month as a year-fraction is an ugly repeating decimal, and computing it
at all would be Talvrin's own conversion layered on top of what the source
actually published — DATA-002's "never coerce/guess" principle applies to
derived identity, not just values).

Scope decision: BC_30YEARDISPLAY is the Treasury's own display variant of
BC_30YEAR (historically used when 30-year issuance was suspended and the
extrapolation factor differed) — not a distinct tenor, so deliberately not
ingested as a separate curve point, mirroring the BoE connector's own
documented sheet-scope narrowings.

Never coerces or guesses (DATA-002): a missing properties block, an
unparseable date, or a non-numeric yield produces a RecordIssue rather than
a fabricated value or a crash that drops every other point in the feed.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from defusedxml import ElementTree as safe_ET  # type: ignore[import-untyped]

_ATOM_NS = "http://www.w3.org/2005/Atom"
_D_NS = "http://schemas.microsoft.com/ado/2007/08/dataservices"
_M_NS = "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"

#: (XML field name, display label) for every published constant-maturity
#: tenor, in ascending maturity order. BC_30YEARDISPLAY is deliberately
#: excluded — see module docstring.
TENOR_FIELDS: tuple[tuple[str, str], ...] = (
    ("BC_1MONTH", "1 Month"),
    ("BC_1_5MONTH", "1.5 Month"),
    ("BC_2MONTH", "2 Month"),
    ("BC_3MONTH", "3 Month"),
    ("BC_4MONTH", "4 Month"),
    ("BC_6MONTH", "6 Month"),
    ("BC_1YEAR", "1 Year"),
    ("BC_2YEAR", "2 Year"),
    ("BC_3YEAR", "3 Year"),
    ("BC_5YEAR", "5 Year"),
    ("BC_7YEAR", "7 Year"),
    ("BC_10YEAR", "10 Year"),
    ("BC_20YEAR", "20 Year"),
    ("BC_30YEAR", "30 Year"),
)


@dataclass(frozen=True)
class CurvePointCandidate:
    curve_date: dt.date
    tenor_field: str
    tenor_label: str
    par_yield_pct: Decimal


@dataclass(frozen=True)
class RecordIssue:
    context: str
    reason: str


def parse_yield_curve(xml_bytes: bytes) -> list[CurvePointCandidate | RecordIssue]:
    try:
        root = safe_ET.fromstring(xml_bytes)
    except Exception as exc:  # noqa: BLE001 - any parse failure means QUARANTINED, not a crash
        return [RecordIssue(context="feed", reason=f"not well-formed XML: {exc}")]

    results: list[CurvePointCandidate | RecordIssue] = []
    for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
        properties = entry.find(f"{{{_ATOM_NS}}}content/{{{_M_NS}}}properties")
        if properties is None:
            results.append(RecordIssue(context="entry", reason="no m:properties element found"))
            continue

        date_el = properties.find(f"{{{_D_NS}}}NEW_DATE")
        if date_el is None or not date_el.text:
            results.append(RecordIssue(context="entry", reason="no NEW_DATE field"))
            continue
        try:
            curve_date = dt.datetime.fromisoformat(date_el.text).date()
        except ValueError:
            results.append(
                RecordIssue(context="entry", reason=f"unparseable NEW_DATE: {date_el.text!r}")
            )
            continue

        for field_name, label in TENOR_FIELDS:
            field_el = properties.find(f"{{{_D_NS}}}{field_name}")
            if field_el is None or not field_el.text:
                # Tenor not published for this date (e.g. BC_1_5MONTH was
                # only added to the feed in 2024) - not an issue, just
                # absent, same as a missing column for an older row.
                continue
            try:
                par_yield_pct = Decimal(field_el.text)
            except InvalidOperation:
                results.append(
                    RecordIssue(
                        context=f"{curve_date.isoformat()} {field_name}",
                        reason=f"non-numeric par yield: {field_el.text!r}",
                    )
                )
                continue
            results.append(
                CurvePointCandidate(
                    curve_date=curve_date,
                    tenor_field=field_name,
                    tenor_label=label,
                    par_yield_pct=par_yield_pct,
                )
            )

    return results
