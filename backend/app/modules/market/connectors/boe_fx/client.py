"""Thin HTTP wrapper around the Bank of England's own daily GBP spot
exchange rate database (the Interactive Statistical Database's CSV export,
series XUDLUSS - "Spot exchange rate, US dollar into Sterling", i.e. USD
per 1 GBP) - fully public, no login, no bot-protection, live-verified
2026-09-24: a plain GET with an honest User-Agent gets a direct 200 OK and
a clean `DATE,XUDLUSS` CSV, same domain/licence (Open Government Licence
v3.0, commercial reuse permitted with attribution) as boe_yield_curve's
connector, whose own docstring documents the same generic-library-string
filter this reuses the honest User-Agent workaround for.

This is a genuinely different source than Frankfurter (ECB-blended rates)
for the same FX_SPOT_RATE metric - the whole point of building it is to
give reconciliation.py's cross-source comparison something real to
compare, for the first time, on a currency pair already in scope
(GBP/USD - see FX_PILOT_QUERIES).
"""

import datetime as dt

import httpx

_IADB_CSV_URL = "https://www.bankofengland.co.uk/boeapps/database/_iadb-FromShowColumns.asp"
_USD_INTO_STERLING_SERIES_CODE = "XUDLUSS"
_USER_AGENT = "TalvrinResearchBot/1.0 (+https://zoikogroup.com)"

# The database only ever returns rows for days it actually has a published
# rate for (verified: no blank/holiday rows) - a wide-enough window just
# guarantees at least one real business day is included even across a long
# weekend or bank holiday cluster, without needing to know which days those
# are ahead of time.
_LOOKBACK_DAYS = 10


def _format_date(date: dt.date) -> str:
    return date.strftime("%d/%b/%Y")


async def fetch_gbp_usd_spot_rates(
    client: httpx.AsyncClient, *, now: dt.datetime | None = None
) -> httpx.Response:
    today = (now or dt.datetime.now(dt.UTC)).date()
    date_from = today - dt.timedelta(days=_LOOKBACK_DAYS)
    return await client.get(
        _IADB_CSV_URL,
        params={
            "csv.x": "1",
            "Datefrom": _format_date(date_from),
            "Dateto": _format_date(today),
            "SeriesCodes": _USD_INTO_STERLING_SERIES_CODE,
            "CSVF": "TN",
            "UsingCodes": "Y",
            "VPD": "Y",
            "VFD": "N",
        },
        headers={"User-Agent": _USER_AGENT},
        timeout=30.0,
    )


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
