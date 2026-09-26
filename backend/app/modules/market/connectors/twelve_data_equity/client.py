"""Thin HTTP wrapper around Twelve Data's time_series endpoint. Requires a
free API key (backend/app/core/config.py's twelve_data_api_key) — unlike
Frankfurter and DBnomics, there is no fully key-free path to real
per-symbol trading data. Verified live (2026-09-18, re-confirmed
2026-09-24): Twelve Data's public "demo" key exists but only serves a
small fixed whitelist of US large-cap symbols (e.g. AAPL) — every other
symbol, including any LSE-listed one, gets refused with the same generic
401, so the demo key cannot stand in for a real key here.

symbol/exchange are separate query parameters, not a combined dotted
string — confirmed live via Twelve Data's key-free /symbol_search
endpoint, e.g. Vodafone resolves to symbol="VOD", exchange="LSE", not
"VOD.LSE".
"""

import datetime as dt

import httpx

TIME_SERIES_URL = "https://api.twelvedata.com/time_series"


async def fetch_daily_series(
    client: httpx.AsyncClient,
    *,
    symbol: str,
    exchange: str,
    api_key: str,
    outputsize: int = 1,
) -> httpx.Response:
    return await client.get(
        TIME_SERIES_URL,
        params={
            "symbol": symbol,
            "exchange": exchange,
            "interval": "1day",
            "outputsize": str(outputsize),
            "apikey": api_key,
        },
        timeout=30.0,
    )


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
