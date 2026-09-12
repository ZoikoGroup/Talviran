"""Login rate limiting (SEC-001 §7.1).

The spec asks for limits "per account, IP/device/risk cluster and endpoint",
and for "progressive friction ... without disclosing account existence".

Two counters, both of which must pass:

  * **per identifier** — stops someone grinding a password list against one
    known address;
  * **per client IP** — stops someone spraying one common password across many
    addresses, which the per-identifier counter alone never sees.

Counting is a fixed window rather than a sliding one. A fixed window lets a
burst straddle the boundary and briefly allow up to 2× the limit; that is a
poor trade for a public API, but for interactive login it costs one extra
handful of attempts and avoids keeping a timestamp set per key in Redis.

Being rate-limited is reported the same way to every caller and never says
whether the address exists — the limit applies to unknown addresses too,
precisely so that it cannot be used as an oracle.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

#: Generous enough not to trip a person who has genuinely forgotten, tight
#: enough that online guessing is hopeless against an Argon2id hash.
MAX_ATTEMPTS_PER_IDENTIFIER = 10
MAX_ATTEMPTS_PER_IP = 30
WINDOW_SECONDS = 15 * 60


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


def _key(scope: str, value: str) -> str:
    return f"auth:attempts:{scope}:{value.lower()}"


async def check_and_count(
    redis: Redis, *, identifier: str, client_ip: str
) -> RateLimitDecision:
    """Records an attempt and says whether it may proceed.

    Counting happens before the credential check, so a blocked caller never
    reaches the password comparison — the expensive part, and the part with
    observable timing.
    """
    limits = (
        (_key("id", identifier), MAX_ATTEMPTS_PER_IDENTIFIER),
        (_key("ip", client_ip), MAX_ATTEMPTS_PER_IP),
    )

    pipe = redis.pipeline()
    for key, _ in limits:
        pipe.incr(key)
    counts: list[int] = await pipe.execute()

    # Set the window only on the counter that just started it. `EXPIRE ... NX`
    # would express this in one command but was added in Redis 7.0, and there
    # is no reason for a login limiter to require a specific server version.
    fresh = [key for (key, _), count in zip(limits, counts, strict=True) if count == 1]
    if fresh:
        pipe = redis.pipeline()
        for key in fresh:
            pipe.expire(key, WINDOW_SECONDS)
        await pipe.execute()

    for (key, limit), count in zip(limits, counts, strict=True):
        if count > limit:
            ttl = await redis.ttl(key)
            if ttl < 0:
                # A key with no expiry would lock this identifier out forever
                # — the one real cost of setting the TTL in a second command.
                # Repair it rather than leaving someone permanently blocked.
                await redis.expire(key, WINDOW_SECONDS)
                ttl = WINDOW_SECONDS
            return RateLimitDecision(allowed=False, retry_after_seconds=max(ttl, 1))
    return RateLimitDecision(allowed=True)


async def clear(redis: Redis, *, identifier: str, client_ip: str) -> None:
    """Resets the counters after a successful sign-in, so a person who
    mistyped a few times is not left near the limit."""
    await redis.delete(_key("id", identifier), _key("ip", client_ip))
