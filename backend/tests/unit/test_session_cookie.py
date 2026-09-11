"""SEC-001 §8.1 / §41 session cookie flags. No database required."""

import datetime as dt

import pytest
from fastapi import Response

from app.modules.identity.cookies import (
    SESSION_COOKIE_NAME,
    CookiePolicy,
    clear_session_cookie,
    set_session_cookie,
)

NOW = dt.datetime(2026, 9, 11, 12, 0, tzinfo=dt.UTC)


def _header(response: Response) -> str:
    return response.headers["set-cookie"]


def _set(environment: str = "production") -> Response:
    response = Response()
    set_session_cookie(
        response,
        token="a-session-token",
        expires_at=NOW + dt.timedelta(days=30),
        policy=CookiePolicy.for_environment(environment),
        now=NOW,
    )
    return response


def test_cookie_is_httponly() -> None:
    """The flag that keeps the token out of reach of JavaScript, and so out
    of reach of an XSS payload."""
    assert "HttpOnly" in _header(_set())


def test_cookie_is_secure_in_production() -> None:
    assert "Secure" in _header(_set("production"))


@pytest.mark.parametrize("environment", ["staging", "prod", "anything-else"])
def test_secure_defaults_on_for_unknown_environments(environment: str) -> None:
    """Fails closed: a typo in the environment name must not silently ship a
    cookie that travels over plain http."""
    assert "Secure" in _header(_set(environment))


@pytest.mark.parametrize("environment", ["development", "test", "DEVELOPMENT"])
def test_secure_is_relaxed_only_for_local_development(environment: str) -> None:
    """Chrome rejects a Secure cookie on http://localhost, so leaving it on
    would make local login impossible — and the usual "fix" is someone
    deleting the flag everywhere."""
    assert "Secure" not in _header(_set(environment))


def test_samesite_is_lax() -> None:
    """Blocks the cross-site POST that CSRF relies on, while still arriving
    when a user follows an emailed link — which Strict would not."""
    assert "SameSite=lax" in _header(_set())


def test_cookie_is_scoped_to_the_whole_site() -> None:
    assert "Path=/" in _header(_set())


def test_cookie_is_host_only() -> None:
    """No Domain attribute, so the session is not handed to sibling
    subdomains that may be less trusted."""
    assert "Domain=" not in _header(_set())


def test_max_age_is_derived_from_the_expiry() -> None:
    """Browser and database must not disagree about when the session ends."""
    assert f"Max-Age={30 * 24 * 3600}" in _header(_set())


def test_already_expired_session_yields_max_age_zero() -> None:
    response = Response()
    set_session_cookie(
        response,
        token="stale",
        expires_at=NOW - dt.timedelta(days=1),
        policy=CookiePolicy.for_environment("production"),
        now=NOW,
    )
    assert "Max-Age=0" in _header(response)


def test_clearing_matches_the_attributes_used_when_setting() -> None:
    """A browser will not replace a cookie whose path or flags differ — a
    mismatch here leaves the old cookie being sent on every request."""
    response = Response()
    clear_session_cookie(response, policy=CookiePolicy.for_environment("production"))
    header = _header(response)
    assert SESSION_COOKIE_NAME in header
    assert "Path=/" in header
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=lax" in header
