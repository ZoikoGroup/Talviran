"""Thin HTTP wrapper around Frankfurter's exchange-rate API. Built against
v2 (/v2/rates), which Frankfurter's own root endpoint labels "current" —
v1 (/v1/latest) is labelled "frozen" and its responses carry a
`deprecation` header, so a new connector has no reason to build against it.
Fully public, free, no API key, no bot-protection observed (verified: a
plain HTTP client gets a direct 200 OK). Rates are blended from
central-bank sources including the ECB.
"""

import datetime as dt

import httpx

RATES_URL = "https://api.frankfurter.dev/v2/rates"


async def fetch_rates(
    client: httpx.AsyncClient, *, base_currency: str, quote_currencies: tuple[str, ...]
) -> httpx.Response:
    return await client.get(
        RATES_URL,
        params={"base": base_currency, "quotes": ",".join(quote_currencies)},
        timeout=30.0,
    )


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
