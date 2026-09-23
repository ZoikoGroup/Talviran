"""Thin HTTP wrapper around UK DMO's published static /media/ PDFs — this
project's own pinned-methodology source (see calculation/specs/
gilt_price_yield_v1/implementation.py's docstring and its golden corpus)
plus, as of 2026-09-23, the GEMM Guidebook (the DMO/Primary Dealer market
structure guide) for real document-corpus growth beyond a single PDF.

Unlike dmo.gov.uk's `/data/*report` endpoints (confirmed Radware-bot-
blocked for any automated client - see market/connectors/dmo_gilts/
client.py's docstring), these are static `/media/` asset paths. Both
verified live and reachable by a plain httpx client - the yield
conventions PDF on 2026-09-18, the GEMM Guidebook on 2026-09-23 (200,
real `application/pdf` content, byte-exact against Content-Length each
time) - a genuinely different access path, not evidence the earlier
block was ever lifted.
"""

import datetime as dt

import httpx

YIELD_CONVENTIONS_PDF_URL = "https://www.dmo.gov.uk/media/ftjpyv1z/yldconv.pdf"
# "A guide to the roles of the DMO and Primary Dealers (GEMMs) in the UK
# government bond market", dated 20/09/21 - the most recent edition found
# via a live search of dmo.gov.uk, not guessed or assumed current.
GEMM_GUIDEBOOK_PDF_URL = "https://dmo.gov.uk/media/22bbjndz/guidebook200921.pdf"

# Same reasoning as boe_yield_curve/client.py's _USER_AGENT: an honest,
# self-identifying UA, not a spoofed browser string - this is what a real
# request from this codebase looks like, not evasion of a block.
_USER_AGENT = "Talvrin/0.1 (+https://zoikogroup.com; contact: dev@zoikogroup.com)"


async def fetch_yield_conventions_pdf(client: httpx.AsyncClient) -> httpx.Response:
    return await client.get(
        YIELD_CONVENTIONS_PDF_URL, timeout=30.0, headers={"User-Agent": _USER_AGENT}
    )


async def fetch_gemm_guidebook_pdf(client: httpx.AsyncClient) -> httpx.Response:
    return await client.get(
        GEMM_GUIDEBOOK_PDF_URL, timeout=30.0, headers={"User-Agent": _USER_AGENT}
    )


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
