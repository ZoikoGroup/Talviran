"""Thin HTTP wrapper around UK DMO's published gilt price/yield methodology
PDF — this project's own pinned-methodology source (see calculation/specs/
gilt_price_yield_v1/implementation.py's docstring and its golden corpus).

Unlike dmo.gov.uk's `/data/*report` endpoints (confirmed Radware-bot-
blocked for any automated client - see market/connectors/dmo_gilts/
client.py's docstring), this is a static `/media/` asset path. Verified
live and reachable by a plain httpx client on 2026-09-18 (200, real
`application/pdf` content, byte-exact against Content-Length) - this is a
genuinely different access path, not evidence the earlier block was ever
lifted.
"""

import datetime as dt

import httpx

YIELD_CONVENTIONS_PDF_URL = "https://www.dmo.gov.uk/media/ftjpyv1z/yldconv.pdf"

# Same reasoning as boe_yield_curve/client.py's _USER_AGENT: an honest,
# self-identifying UA, not a spoofed browser string - this is what a real
# request from this codebase looks like, not evasion of a block.
_USER_AGENT = "Talvrin/0.1 (+https://zoikogroup.com; contact: dev@zoikogroup.com)"


async def fetch_yield_conventions_pdf(client: httpx.AsyncClient) -> httpx.Response:
    return await client.get(
        YIELD_CONVENTIONS_PDF_URL, timeout=30.0, headers={"User-Agent": _USER_AGENT}
    )


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
