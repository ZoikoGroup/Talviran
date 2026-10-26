"""Thin HTTP wrapper around the US Treasury's daily par yield curve feed —
fully public, no login, no bot-protection (verified: a plain curl gets a
direct 200 OK, with `Access-Control-Allow-Origin: *`) — unlike the DMO
gilts feed, which blocks automated clients with a Radware challenge.

Published by home.treasury.gov's own ATOM/OData feed, NOT the separate
api.fiscaldata.treasury.gov REST API — that one only carries the average
interest rate on outstanding debt by security type, a different dataset
from the par yield curve (the constant-maturity series behind every
"10-year Treasury yield" headline figure). Confirmed live 2026-10-22.

The `field_tdr_date_value` query parameter is REQUIRED, not optional:
omitting it returns an empty feed (verified live: 200 OK, 0 entries, 102
bytes) rather than defaulting to the current year.
"""

import datetime as dt

import httpx

YIELD_CURVE_XML_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
)


async def fetch_yield_curve_xml(client: httpx.AsyncClient, *, year: int) -> httpx.Response:
    return await client.get(
        YIELD_CURVE_XML_URL,
        params={"data": "daily_treasury_yield_curve", "field_tdr_date_value": str(year)},
        timeout=30.0,
        follow_redirects=True,
    )


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
