"""Thin HTTP wrapper around Tradeweb Market InSite's authenticated gilt
closing-price export - real UK & European sovereign closing prices
(clean/dirty price, yield, modified duration, accrued interest), not a
model-implied estimate. Live-verified 2026-09-23 with a real registered
account (TRADEWEB_USERNAME/TRADEWEB_PASSWORD in Settings): a real 126KB
CSV, 972 rows, Bills/Conventional/other-sovereign rows.

DMO's own historical-prices page now officially points here
(reports.tradeweb.com/closing-prices/gilts/) as the current source for
free EOD gilt closing prices - this isn't a workaround, it's the
publisher's own named replacement for the discontinued DMO file
download. Licensed for "non-professional and non-commercial use" only
(the site's own export confirmation dialog says so explicitly, with a
"contact us for commercial use" link) - fine for Talvrin's current
development stage, not a substitute for a real commercial data
agreement before any paid launch.

Unlike every other connector in this codebase, this one needs a real
authenticated session - there is no anonymous/API-key path. The site is
classic ASP.NET WebForms: a login click and the export button are both
`__doPostBack` calls needing the page's own current `__VIEWSTATE`/
`__VIEWSTATEGENERATOR`/`__EVENTVALIDATION` hidden fields, fetched fresh
each time (they're session/request-specific, not stable constants).

Deliberately NOT meant to run repeatedly/rapidly - two ReadTimeouts hit
during live verification after one clean successful run, consistent
with a real rate-limit on the login endpoint. EOD close data only
updates once a day anyway; this connector is meant to run at most once
a day, never in a tight loop or a test suite.
"""

import re

import httpx

LOGIN_URL = "https://reports.tradeweb.com/account/login/?ReturnUrl=%2fclosing-prices%2fgilts%2f"
_USER_AGENT = "Talvrin/0.1 (+https://zoikogroup.com; contact: dev@zoikogroup.com)"

_LOGIN_EVENT_TARGET = "ctl00$MainContent$LoginUser$LoginButton"
_EXPORT_EVENT_TARGET = "ctl00$ctl00$MainContent$MainContent$ExportButton"
_USERNAME_FIELD = "ctl00$MainContent$LoginUser$UserName"
_PASSWORD_FIELD = "ctl00$MainContent$LoginUser$Password"

_HIDDEN_FIELD_NAMES = ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION")


class TradewebAuthError(Exception):
    """Login or the export postback failed - the message never includes
    the password (only field names/lengths and response status/URL)."""


def _extract_hidden_field(html: str, field_id: str) -> str:
    match = re.search(rf'id="{field_id}" value="([^"]*)"', html)
    if match is None:
        raise TradewebAuthError(
            f"could not find hidden field {field_id!r} on the page - the site's "
            "form structure may have changed"
        )
    return match.group(1)


def _hidden_fields(html: str) -> dict[str, str]:
    return {name: _extract_hidden_field(html, name) for name in _HIDDEN_FIELD_NAMES}


async def fetch_gilt_closing_prices_csv(
    client: httpx.AsyncClient, *, username: str, password: str
) -> httpx.Response:
    """The full authenticated flow in one call: GET the login page, POST
    credentials, then POST the export button's own postback target,
    returning the raw CSV response. `client` must be dedicated to this
    call (not shared with unrelated requests) - the export step depends
    on session cookies the login step sets.
    """
    headers = {"User-Agent": _USER_AGENT}

    login_page = await client.get(LOGIN_URL, headers=headers, timeout=30.0)
    login_fields = _hidden_fields(login_page.text)
    login_response = await client.post(
        str(login_page.url),
        headers=headers,
        timeout=30.0,
        data={
            "__EVENTTARGET": _LOGIN_EVENT_TARGET,
            "__EVENTARGUMENT": "",
            **login_fields,
            _USERNAME_FIELD: username,
            _PASSWORD_FIELD: password,
        },
    )
    if "closing-prices" not in str(login_response.url):
        raise TradewebAuthError(
            f"login did not land on the closing-prices page (landed on "
            f"{login_response.url}) - the account may be invalid, locked, or "
            "the login endpoint may be rate-limiting rapid attempts"
        )

    export_fields = _hidden_fields(login_response.text)
    export_response = await client.post(
        str(login_response.url),
        headers=headers,
        timeout=30.0,
        data={
            "__EVENTTARGET": _EXPORT_EVENT_TARGET,
            "__EVENTARGUMENT": "",
            **export_fields,
        },
    )
    if export_response.status_code != 200:
        raise TradewebAuthError(
            f"export postback returned {export_response.status_code}, expected 200"
        )
    return export_response
