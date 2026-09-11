"""Session cookie construction (SEC-001 §8.1, §41).

§8.1: "Secure, HttpOnly, SameSite-protected cookies for browser sessions; no
tokens in localStorage for privileged session material." §41 lists storing
session tokens in localStorage as a prohibited anti-pattern outright. This
module is the only place the cookie is shaped, so those flags cannot be
forgotten at one call site.

`Secure` is relaxed for local development only — Chrome refuses a `Secure`
cookie over plain http://localhost, so leaving it on unconditionally would
make it impossible to log in while developing, and the usual "fix" for that
is someone quietly deleting the flag everywhere. Better to bind it to the
environment in one visible place.

SameSite is `lax`, not `strict`: `strict` would drop the cookie when a user
arrives from an external link (an emailed password-reset, for instance) and
they would appear signed out. `lax` still blocks the cross-site POST that
CSRF depends on.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from fastapi import Response

#: Host-only by default. No `Domain` attribute is set, so the cookie is not
#: shared with sibling subdomains unless that is explicitly configured later.
SESSION_COOKIE_NAME = "talvrin_session"
COOKIE_PATH = "/"
SAMESITE: Literal["lax", "strict", "none"] = "lax"


@dataclass(frozen=True)
class CookiePolicy:
    """Resolved per environment so `Secure` is never silently off in prod."""

    secure: bool

    @classmethod
    def for_environment(cls, environment: str) -> CookiePolicy:
        # Anything that is not explicitly local development gets Secure.
        # Failing closed matters more here than convenience.
        return cls(secure=environment.lower() not in {"development", "test"})


def set_session_cookie(
    response: Response,
    *,
    token: str,
    expires_at: dt.datetime,
    policy: CookiePolicy,
    now: dt.datetime | None = None,
) -> None:
    """Attaches the session cookie.

    `max_age` is derived from the absolute expiry rather than passed in, so
    the browser and the database cannot disagree about when the session ends.
    """
    current = now or dt.datetime.now(dt.UTC)
    max_age = max(0, int((expires_at - current).total_seconds()))
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        path=COOKIE_PATH,
        httponly=True,
        secure=policy.secure,
        samesite=SAMESITE,
    )


def clear_session_cookie(response: Response, *, policy: CookiePolicy) -> None:
    """Removes the cookie on sign-out.

    The attributes must match the ones used when setting it — a browser will
    not replace a cookie whose path or security attributes differ, and the
    stale one would keep being sent.
    """
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path=COOKIE_PATH,
        httponly=True,
        secure=policy.secure,
        samesite=SAMESITE,
    )
