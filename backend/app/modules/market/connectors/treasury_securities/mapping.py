"""Parsing/normalisation for TreasuryDirect's auctioned-securities feed —
isolated from the connector so "how do we read this specific feed" is
unit-testable without any network or DB dependency.

Scope decision: only Note, Bond and TIPS parse into a usable candidate.
Bills are discount instruments (no coupon at all — priced via
investmentRate, not interestRate) and FRNs pay a floating spread over a
reference rate (no fixed coupon either), neither of which fits
reference.FiSovereignTerms' fixed-coupon shape (coupon_rate is NOT NULL —
see its own docstring: "the gilt/Treasury asset-adapter table"). This
mirrors onboard_all_gilts.py's own index-linked-gilt scope narrowing:
each needs its own terms-adapter shape, not a value forced into this one.
A Bill/FRN record is a documented RecordIssue, never a fabricated coupon.

TIPS are classified via the feed's own `inflationProtected` flag, not the
`securityType` field — TreasuryDirect reports TIPS as securityType="Note"
(confirmed live: querying type=TIPS returns inflationProtected="Yes" rows
indistinguishable from a plain Note by securityType alone).

Never coerces or guesses (DATA-002): a missing cusip, an unparseable date,
or a missing/non-numeric coupon produces a RecordIssue rather than a
fabricated value.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class TreasurySecurityCandidate:
    cusip: str
    security_type: str  # "Note" | "Bond" | "TIPS"
    security_term: str  # the source's own term label, e.g. "10-Year"
    issue_date: dt.date
    maturity_date: dt.date
    coupon_rate: Decimal


@dataclass(frozen=True)
class RecordIssue:
    context: str
    reason: str


def _parse_td_date(raw: object) -> dt.date | None:
    # TreasuryDirect dates are ISO datetimes at midnight, e.g.
    # "2026-10-31T00:00:00" - only the date part is ever meaningful.
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def parse_auctioned_securities(
    records: list[dict[str, Any]], *, queried_type: str
) -> list[TreasurySecurityCandidate | RecordIssue]:
    results: list[TreasurySecurityCandidate | RecordIssue] = []
    for record in records:
        cusip = record.get("cusip")
        if not cusip or not isinstance(cusip, str):
            results.append(RecordIssue(context="record", reason="missing cusip"))
            continue

        if record.get("floatingRate") == "Yes":
            results.append(
                RecordIssue(context=cusip, reason="floating-rate note - no fixed coupon to store")
            )
            continue
        security_type = "TIPS" if record.get("inflationProtected") == "Yes" else queried_type

        issue_date = _parse_td_date(record.get("issueDate"))
        maturity_date = _parse_td_date(record.get("maturityDate"))
        if issue_date is None or maturity_date is None:
            results.append(RecordIssue(context=cusip, reason="unparseable issue/maturity date"))
            continue

        coupon_raw = record.get("interestRate")
        if not coupon_raw or not isinstance(coupon_raw, str):
            results.append(
                RecordIssue(context=cusip, reason="no interestRate (discount instrument?)")
            )
            continue
        try:
            coupon_rate = Decimal(coupon_raw)
        except InvalidOperation:
            results.append(
                RecordIssue(context=cusip, reason=f"non-numeric interestRate: {coupon_raw!r}")
            )
            continue

        results.append(
            TreasurySecurityCandidate(
                cusip=cusip,
                security_type=security_type,
                security_term=str(record.get("securityTerm") or ""),
                issue_date=issue_date,
                maturity_date=maturity_date,
                coupon_rate=coupon_rate,
            )
        )
    return results
