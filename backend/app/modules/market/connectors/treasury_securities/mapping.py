"""Parsing/normalisation for TreasuryDirect's auctioned-securities feed —
isolated from the connector so "how do we read this specific feed" is
unit-testable without any network or DB dependency.

Three candidate shapes, one per terms-adapter table (reference/models.py):
- `TreasurySecurityCandidate` (Note, Bond, TIPS) -> FiSovereignTerms, a
  fixed semi-annual coupon.
- `TreasuryDiscountCandidate` (Bill, incl. Cash Management Bills) ->
  FiSovereignDiscountTerms, no coupon at all.
- `TreasuryFrnCandidate` (FRN) -> FiSovereignFrnTerms, a floating spread
  over an index rate, no fixed coupon either.

Each needs its own terms-adapter shape, not a value forced into
FiSovereignTerms (coupon_rate is NOT NULL there — see its own docstring:
"the gilt/Treasury asset-adapter table"). This mirrors
onboard_all_gilts.py's own index-linked-gilt scope narrowing.

TIPS are classified via the feed's own `inflationProtected` flag, not the
`securityType` field — TreasuryDirect reports TIPS as securityType="Note"
(confirmed live: querying type=TIPS returns inflationProtected="Yes" rows
indistinguishable from a plain Note by securityType alone). FRNs are
likewise reported as securityType="Note" with floatingRate="Yes" (confirmed
live 2026-10-26, querying type=FRN). Cash Management Bills are reported as
securityType="Bill" with cashManagementBill="Yes" (confirmed live
2026-10-26, querying type=Bill) — not a distinct queryable type at all.

Never coerces or guesses (DATA-002): a missing cusip, an unparseable date,
or a missing/non-numeric rate field produces a RecordIssue rather than a
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
class TreasuryDiscountCandidate:
    cusip: str
    security_term: str
    issue_date: dt.date
    maturity_date: dt.date
    high_rate: Decimal  # percent, the auction's own discount rate
    investment_rate: Decimal  # percent, coupon-equivalent (bond-equivalent) yield
    is_cash_management_bill: bool


@dataclass(frozen=True)
class TreasuryFrnCandidate:
    cusip: str
    security_term: str
    issue_date: dt.date
    maturity_date: dt.date
    spread: Decimal  # percent, over the index rate
    index_determination_rate: Decimal  # percent, at this security's own auction
    frequency_of_interest_payments: str  # e.g. "Quarterly"


@dataclass(frozen=True)
class RecordIssue:
    context: str
    reason: str


_TreasuryCandidate = (
    TreasurySecurityCandidate | TreasuryDiscountCandidate | TreasuryFrnCandidate
)


def _parse_td_date(raw: object) -> dt.date | None:
    # TreasuryDirect dates are ISO datetimes at midnight, e.g.
    # "2026-10-31T00:00:00" - only the date part is ever meaningful.
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def _parse_decimal(raw: object) -> Decimal | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _parse_fixed_coupon_record(
    record: dict[str, Any], *, cusip: str, queried_type: str
) -> _TreasuryCandidate | RecordIssue:
    if record.get("floatingRate") == "Yes":
        return RecordIssue(context=cusip, reason="floating-rate note - query type=FRN instead")
    security_type = "TIPS" if record.get("inflationProtected") == "Yes" else queried_type

    issue_date = _parse_td_date(record.get("issueDate"))
    maturity_date = _parse_td_date(record.get("maturityDate"))
    if issue_date is None or maturity_date is None:
        return RecordIssue(context=cusip, reason="unparseable issue/maturity date")

    coupon_raw = record.get("interestRate")
    if not coupon_raw or not isinstance(coupon_raw, str):
        return RecordIssue(context=cusip, reason="no interestRate (discount instrument?)")
    coupon_rate = _parse_decimal(coupon_raw)
    if coupon_rate is None:
        return RecordIssue(context=cusip, reason=f"non-numeric interestRate: {coupon_raw!r}")

    return TreasurySecurityCandidate(
        cusip=cusip,
        security_type=security_type,
        security_term=str(record.get("securityTerm") or ""),
        issue_date=issue_date,
        maturity_date=maturity_date,
        coupon_rate=coupon_rate,
    )


def _parse_bill_record(record: dict[str, Any], *, cusip: str) -> _TreasuryCandidate | RecordIssue:
    issue_date = _parse_td_date(record.get("issueDate"))
    maturity_date = _parse_td_date(record.get("maturityDate"))
    if issue_date is None or maturity_date is None:
        return RecordIssue(context=cusip, reason="unparseable issue/maturity date")

    high_rate = _parse_decimal(record.get("highRate"))
    if high_rate is None:
        return RecordIssue(context=cusip, reason="no/non-numeric highRate")
    investment_rate = _parse_decimal(record.get("investmentRate"))
    if investment_rate is None:
        return RecordIssue(context=cusip, reason="no/non-numeric investmentRate")

    return TreasuryDiscountCandidate(
        cusip=cusip,
        security_term=str(record.get("securityTerm") or ""),
        issue_date=issue_date,
        maturity_date=maturity_date,
        high_rate=high_rate,
        investment_rate=investment_rate,
        is_cash_management_bill=record.get("cashManagementBill") == "Yes",
    )


def _parse_frn_record(record: dict[str, Any], *, cusip: str) -> _TreasuryCandidate | RecordIssue:
    if record.get("floatingRate") != "Yes":
        return RecordIssue(context=cusip, reason="type=FRN query returned a non-floating record")

    issue_date = _parse_td_date(record.get("issueDate"))
    maturity_date = _parse_td_date(record.get("maturityDate"))
    if issue_date is None or maturity_date is None:
        return RecordIssue(context=cusip, reason="unparseable issue/maturity date")

    spread = _parse_decimal(record.get("spread"))
    if spread is None:
        return RecordIssue(context=cusip, reason="no/non-numeric spread")
    index_determination_rate = _parse_decimal(record.get("indexDeterminationRate"))
    if index_determination_rate is None:
        return RecordIssue(context=cusip, reason="no/non-numeric indexDeterminationRate")
    frequency = record.get("frequencyOfInterestPayments")
    if not frequency or not isinstance(frequency, str):
        return RecordIssue(context=cusip, reason="no frequencyOfInterestPayments")

    return TreasuryFrnCandidate(
        cusip=cusip,
        security_term=str(record.get("securityTerm") or ""),
        issue_date=issue_date,
        maturity_date=maturity_date,
        spread=spread,
        index_determination_rate=index_determination_rate,
        frequency_of_interest_payments=frequency,
    )


def parse_auctioned_securities(
    records: list[dict[str, Any]], *, queried_type: str
) -> list[_TreasuryCandidate | RecordIssue]:
    results: list[_TreasuryCandidate | RecordIssue] = []
    for record in records:
        cusip = record.get("cusip")
        if not cusip or not isinstance(cusip, str):
            results.append(RecordIssue(context="record", reason="missing cusip"))
            continue

        if queried_type == "Bill":
            results.append(_parse_bill_record(record, cusip=cusip))
        elif queried_type == "FRN":
            results.append(_parse_frn_record(record, cusip=cusip))
        else:
            results.append(
                _parse_fixed_coupon_record(record, cusip=cusip, queried_type=queried_type)
            )
    return results
