"""Session tokens (SEC-001 §8).

The invariant this module exists to enforce: **the database never holds a
usable session token.** The raw token goes to the browser cookie and nowhere
else; only its SHA-256 digest is persisted. A dump of `identity.session` is
then worthless for impersonation, which is not true of the common pattern of
storing the token verbatim.

SHA-256 rather than Argon2 here, deliberately. Argon2 is slow by design to
make guessing a low-entropy human password expensive. These tokens carry 256
bits of entropy from the OS, so there is nothing to guess — and session
lookup happens on every single request, where a deliberately slow hash would
be a self-inflicted denial of service.

Expiry is two-sided, per §8: `absolute_expiry` caps the total life of a
session regardless of activity, and `idle_expiry` ends one that has gone
quiet. A session needs both — absolute alone lets a stolen cookie live for
days, idle alone lets an active attacker hold a session indefinitely.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
from dataclasses import dataclass

#: 32 bytes of OS entropy; token_urlsafe returns ~43 characters for this.
TOKEN_BYTES = 32

#: §8 requires both bounds. These are launch defaults, not fixed constants —
#: step-up flows may later issue shorter-lived sessions.
DEFAULT_ABSOLUTE_LIFETIME = dt.timedelta(days=30)
DEFAULT_IDLE_TIMEOUT = dt.timedelta(days=7)


def generate_token() -> str:
    """A fresh, high-entropy session token. Never logged, never stored."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """The digest that goes in the database, in place of the token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(stored_hash: str, presented_token: str) -> bool:
    """Compares in constant time.

    A plain `==` on hex digests leaks timing information about how many
    leading characters matched. The tokens are random so this is a thin
    attack, but `compare_digest` costs nothing to use.
    """
    return hmac.compare_digest(stored_hash, hash_token(presented_token))


@dataclass(frozen=True)
class IssuedSession:
    """What a login produces: the token for the cookie, the digest for the
    row, and the two expiry bounds."""

    token: str
    token_hash: str
    issued_at: dt.datetime
    absolute_expiry: dt.datetime
    idle_expiry: dt.datetime


def issue_session(
    *,
    now: dt.datetime | None = None,
    absolute_lifetime: dt.timedelta = DEFAULT_ABSOLUTE_LIFETIME,
    idle_timeout: dt.timedelta = DEFAULT_IDLE_TIMEOUT,
) -> IssuedSession:
    """Mints a session. `now` is injectable so expiry logic is testable
    without sleeping."""
    issued_at = now or dt.datetime.now(dt.UTC)
    token = generate_token()
    return IssuedSession(
        token=token,
        token_hash=hash_token(token),
        issued_at=issued_at,
        absolute_expiry=issued_at + absolute_lifetime,
        idle_expiry=issued_at + idle_timeout,
    )


def slide_idle_expiry(
    *,
    absolute_expiry: dt.datetime,
    now: dt.datetime,
    idle_timeout: dt.timedelta = DEFAULT_IDLE_TIMEOUT,
) -> dt.datetime:
    """Extends the idle window on activity, but never past the absolute cap.

    Without the clamp, a session used once a day would live forever and the
    absolute bound would be decorative.
    """
    return min(now + idle_timeout, absolute_expiry)


def is_expired(
    *,
    absolute_expiry: dt.datetime,
    idle_expiry: dt.datetime,
    revoked_at: dt.datetime | None,
    now: dt.datetime,
) -> bool:
    """True when a session must no longer authenticate a request.

    Revocation is checked first and is unconditional: §8 requires session
    state to be revocable server-side, which is the whole reason sessions are
    rows rather than self-contained signed tokens.
    """
    if revoked_at is not None:
        return True
    return now >= absolute_expiry or now >= idle_expiry
