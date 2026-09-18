"""Thin HTTP wrapper around DBnomics' series endpoint. Fully public, free,
no API key. DBnomics aggregates ~90 official statistical providers into
one consistent API — the pilot series use provider WB (World Bank),
dataset WDI (World Development Indicators). No bot-protection observed
(verified: a plain HTTP client gets a direct 200 OK).
"""

import datetime as dt

import httpx

SERIES_URL_TEMPLATE = "https://api.db.nomics.world/v22/series/{provider_code}/{dataset_code}/{series_code}"


async def fetch_series(
    client: httpx.AsyncClient, *, provider_code: str, dataset_code: str, series_code: str
) -> httpx.Response:
    url = SERIES_URL_TEMPLATE.format(
        provider_code=provider_code, dataset_code=dataset_code, series_code=series_code
    )
    # metadata=false drops DBnomics' large dimensions_values_labels block
    # (every country/indicator name in the whole dataset) that we never
    # use — observations=1 asks for only the latest reported period.
    return await client.get(
        url, params={"observations": "1", "metadata": "false"}, timeout=30.0
    )


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
