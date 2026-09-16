"""Single-use enforcement for password-reset tokens.

Confirmed live against the real Supabase project (2026-09-16): the
`access_token` from a recovery link is an ordinary session access token,
valid for its full ~1 hour lifetime and reusable for repeated calls within
that window — it is not single-use at Supabase's own level. That is a
reasonable design for GoTrue in general (the same token also lets a user view
or update other parts of their profile after verifying their mailbox once),
but it means a leaked or forwarded reset link would otherwise stay live for
an hour and usable more than once through this app's own endpoint.

This closes that gap the same way session tokens already are (§8): Redis
holds a marker keyed by the token's SHA-256 digest — never the token itself
— set only once a password change has actually succeeded, so a call that
fails validation (e.g. a weak new password) leaves the link usable for a
retry rather than burning it on a mistake.
"""

from __future__ import annotations

import hashlib

from redis.asyncio import Redis

#: Matches Supabase's own default access-token lifetime — no reason for our
#: denylist entry to outlive the token it is blocking, which expires on its
#: own after this regardless.
TOKEN_LIFETIME_SECONDS = 60 * 60

_KEY_PREFIX = "auth:spent-reset-token:"


def _key(access_token: str) -> str:
    digest = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
    return f"{_KEY_PREFIX}{digest}"


async def is_spent(redis: Redis, *, access_token: str) -> bool:
    return bool(await redis.exists(_key(access_token)))


async def mark_spent(redis: Redis, *, access_token: str) -> None:
    await redis.set(_key(access_token), "1", ex=TOKEN_LIFETIME_SECONDS)
