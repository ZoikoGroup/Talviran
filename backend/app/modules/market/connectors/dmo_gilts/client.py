"""Thin HTTP wrapper around UK DMO's Gilts in Issue feed.

Uses `xmldatareport?reportCode=D1A`, NOT `ExportReport`/`pdfdatareport` —
both of those redirect to a Radware bot-protection challenge
(validate.perfdrive.com) for any non-browser client. `xmldatareport` was
verified reachable from a real browser session, but a plain `curl` request
against the identical URL (realistic browser User-Agent included) got the
same bot-check redirect. This means an automated client — including this
one — is NOT confirmed to reach this endpoint in practice; `acquire()`
below is written to work if/when it does (e.g. DMO allowlists a production
IP, or the block turns out to be specific to residential/dev-machine
traffic), but as of P1 week 8 this has only been exercised against a real
fixture (tests/fixtures/dmo_gilts_in_issue.xml, captured from a real
browser session), not a live call. See health() for how a caller detects
whether live access currently works.
"""

import datetime as dt

import httpx

GILTS_IN_ISSUE_URL = "https://www.dmo.gov.uk/data/xmldatareport?reportCode=D1A"


async def fetch_gilts_in_issue(client: httpx.AsyncClient) -> httpx.Response:
    return await client.get(GILTS_IN_ISSUE_URL, timeout=30.0)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
