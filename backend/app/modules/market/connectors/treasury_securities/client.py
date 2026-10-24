"""Thin HTTP wrapper around TreasuryDirect's auctioned-securities feed —
fully public, no login, no API key (verified live, 2026-10-22: a plain
curl against `type=Note&days=30` gets a direct 200 OK with real CUSIPs
and coupon rates). Not the same endpoint as `connectors/treasury_yield_curve`
(the par yield curve) — this one carries individual security reference
terms (CUSIP, coupon, maturity), not an aggregate curve.

`/securities/search` (the more general endpoint) also exists but mixes in
not-yet-auctioned announcements with no confirmed interestRate yet —
`/securities/auctioned` only ever returns securities with a completed,
confirmed auction, which is what a reference-terms onboarding needs.
"""

import datetime as dt

import httpx

AUCTIONED_SECURITIES_URL = "https://www.treasurydirect.gov/TA_WS/securities/auctioned"


async def fetch_auctioned_securities(
    client: httpx.AsyncClient, *, security_type: str, days: int
) -> httpx.Response:
    return await client.get(
        AUCTIONED_SECURITIES_URL,
        params={"type": security_type, "days": str(days)},
        timeout=30.0,
        follow_redirects=True,
    )


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
