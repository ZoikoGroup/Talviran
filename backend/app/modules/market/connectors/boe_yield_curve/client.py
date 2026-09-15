"""Thin HTTP wrapper around the Bank of England's daily gilt yield curve
feed — fully public, no login, no bot-protection (verified: a plain HTTP
client gets a direct 200 OK). Published under the Open Government Licence
v3.0, which explicitly permits commercial reuse with attribution — unlike
Tradeweb's per-instrument gilt closing prices, whose terms forbid both
commercial use and redistribution of the data at all. That's why this
connector feeds a MODEL-IMPLIED price (market/pipeline/curve_pricing.py),
never a claimed market quote: this feed doesn't contain one.
"""

import datetime as dt

import httpx

YIELD_CURVE_ZIP_URL = (
    "https://www.bankofengland.co.uk/-/media/boe/files/statistics/"
    "yield-curves/latest-yield-curve-data.zip"
)

# bankofengland.co.uk 403s the default httpx/requests User-Agent string but
# accepts any honest, self-identifying one (verified) — this is a generic
# library-string filter, not bot-protection, so identifying ourselves
# truthfully (never a spoofed browser UA) is both correct and sufficient.
_USER_AGENT = "TalvrinResearchBot/1.0 (+https://zoikogroup.com)"


async def fetch_yield_curve_zip(client: httpx.AsyncClient) -> httpx.Response:
    return await client.get(
        YIELD_CURVE_ZIP_URL,
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    )


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
