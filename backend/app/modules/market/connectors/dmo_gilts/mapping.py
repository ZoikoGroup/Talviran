"""Parsing/normalisation for DMO's Gilts in Issue XML — isolated from the
connector so "how do we read DMO's specific format" is unit-testable
without any network or DB dependency.

Never coerces or guesses (DATA-002): an unparseable coupon, date, or
missing required attribute produces a RecordIssue for that one record
rather than a fabricated value or a crash that drops every other record
in the file.
"""

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# DMO encodes the coupon in the instrument name itself (e.g. "4 1/4%
# Treasury Stock 2036", "1¼% Treasury Gilt 2027") — there is no separate
# coupon attribute in the feed. Both a unicode vulgar-fraction form and an
# ASCII "N/D" form appear in real data, sometimes with a stray space before
# "%" (e.g. "1¼ % Treasury Gilt 2041" — a genuine quirk in DMO's own data,
# not a bug in this parser).
_FRACTION_MAP: dict[str, Decimal] = {
    "¼": Decimal("0.25"),
    "½": Decimal("0.5"),
    "¾": Decimal("0.75"),
    "⅛": Decimal("0.125"),
    "⅜": Decimal("0.375"),
    "⅝": Decimal("0.625"),
    "⅞": Decimal("0.875"),
    "1/8": Decimal("0.125"),
    "1/4": Decimal("0.25"),
    "3/8": Decimal("0.375"),
    "1/2": Decimal("0.5"),
    "5/8": Decimal("0.625"),
    "3/4": Decimal("0.75"),
    "7/8": Decimal("0.875"),
}

_FRACTION_ALTERNATION = "|".join(sorted(_FRACTION_MAP, key=len, reverse=True))
_COUPON_RE = re.compile(rf"^(\d+)?\s*({_FRACTION_ALTERNATION})?\s*%")

GILT_TYPE_CONVENTIONAL = "CONVENTIONAL"
GILT_TYPE_INDEX_LINKED = "INDEX_LINKED"

REQUIRED_ATTRIBUTES = (
    "ISIN_CODE",
    "INSTRUMENT_NAME",
    "INSTRUMENT_TYPE",
    "REDEMPTION_DATE",
    "FIRST_ISSUE_DATE",
    "DIVIDEND_DATES",
    "CLOSE_OF_BUSINESS_DATE",
    "TOTAL_AMOUNT_IN_ISSUE",
)


def parse_coupon_rate(instrument_name: str) -> Decimal | None:
    """Returns None (never a guess) if the leading text doesn't match a
    recognised coupon pattern — e.g. a future DMO format change."""
    match = _COUPON_RE.match(instrument_name.strip())
    if match is None:
        return None
    whole = Decimal(match.group(1)) if match.group(1) else Decimal(0)
    frac_token = match.group(2)
    frac = _FRACTION_MAP[frac_token] if frac_token else Decimal(0)
    return whole + frac


def classify_gilt_type(instrument_type: str) -> str:
    if instrument_type.strip().lower().startswith("index-linked"):
        return GILT_TYPE_INDEX_LINKED
    return GILT_TYPE_CONVENTIONAL


@dataclass(frozen=True)
class GiltReferenceCandidate:
    isin: str
    instrument_name: str
    gilt_type: str
    coupon_rate: Decimal | None
    redemption_date: dt.date
    first_issue_date: dt.date
    dividend_dates: str
    close_of_business_date: dt.date
    total_amount_in_issue: Decimal


@dataclass(frozen=True)
class RecordIssue:
    raw_isin: str | None
    reason: str


def _parse_dmo_date(value: str) -> dt.date:
    return dt.datetime.fromisoformat(value).date()


def normalise_record(attrs: dict[str, str]) -> GiltReferenceCandidate | RecordIssue:
    missing = [key for key in REQUIRED_ATTRIBUTES if not attrs.get(key, "").strip()]
    if missing:
        return RecordIssue(
            raw_isin=attrs.get("ISIN_CODE"),
            reason=f"missing required attribute(s): {', '.join(missing)}",
        )

    try:
        redemption_date = _parse_dmo_date(attrs["REDEMPTION_DATE"])
        first_issue_date = _parse_dmo_date(attrs["FIRST_ISSUE_DATE"])
        close_of_business_date = _parse_dmo_date(attrs["CLOSE_OF_BUSINESS_DATE"])
        total_amount_in_issue = Decimal(attrs["TOTAL_AMOUNT_IN_ISSUE"])
    except (ValueError, InvalidOperation) as exc:
        return RecordIssue(raw_isin=attrs.get("ISIN_CODE"), reason=f"unparseable field: {exc}")

    return GiltReferenceCandidate(
        isin=attrs["ISIN_CODE"],
        instrument_name=attrs["INSTRUMENT_NAME"].strip(),
        gilt_type=classify_gilt_type(attrs["INSTRUMENT_TYPE"]),
        coupon_rate=parse_coupon_rate(attrs["INSTRUMENT_NAME"]),
        redemption_date=redemption_date,
        first_issue_date=first_issue_date,
        dividend_dates=attrs["DIVIDEND_DATES"].strip(),
        close_of_business_date=close_of_business_date,
        total_amount_in_issue=total_amount_in_issue,
    )
