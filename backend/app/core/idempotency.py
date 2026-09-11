"""Idempotency-Key handling (API-001): identical key + identical request
body replays the stored response; the same key with a different body is a
conflict, not a silent overwrite ("just overwrite on collision" is the
tempting first draft and is wrong per spec — API-001 requires the
same-key-different-body case to fail explicitly).

Backed by Redis, not Postgres — an idempotency record is a bounded-
lifetime technical dedup mechanism, not canonical truth (ENG-ARCH-003:
Redis is ephemeral cache, never truth — this is exactly that, not an
exception to it).

No real POST endpoint exists to wire this into yet — P1 week 13 adds the
first one (POST /api/v1/research). Built and tested standalone now, the
same way app.core.pagination was built and tested before Week 4 had
endpoints to use it. `scope` should be widened to include principal_id once
real auth exists (P2) — for now callers pass something stable like the
route path so different endpoints' keys never collide.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

_TTL_SECONDS = 24 * 60 * 60  # API-001 doesn't pin an exact value; revisit
# once a real endpoint's client retry behaviour is known.


class IdempotencyConflictError(Exception):
    """Same Idempotency-Key, different request body. Callers map this to
    ErrorCode.CONFLICT (409) via the canonical envelope."""

    def __init__(self, idempotency_key: str) -> None:
        self.idempotency_key = idempotency_key
        super().__init__(
            f"Idempotency-Key {idempotency_key!r} was already used with a different request body."
        )


@dataclass(frozen=True)
class IdempotentResult:
    status_code: int
    body: dict[str, Any]
    replayed: bool  # True if this came from a prior stored response, not a fresh call


def _redis_key(scope: str, idempotency_key: str) -> str:
    return f"idempotency:{scope}:{idempotency_key}"


def _hash_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


async def run_idempotent(
    redis: Redis,
    *,
    scope: str,
    idempotency_key: str,
    request_body: bytes,
    handler: Callable[[], Awaitable[tuple[int, dict[str, Any]]]],
) -> IdempotentResult:
    key = _redis_key(scope, idempotency_key)
    body_hash = _hash_body(request_body)

    existing_raw = await redis.get(key)
    if existing_raw is not None:
        existing = json.loads(existing_raw)
        if existing["body_hash"] != body_hash:
            raise IdempotencyConflictError(idempotency_key)
        return IdempotentResult(
            status_code=existing["status_code"], body=existing["body"], replayed=True
        )

    status_code, body = await handler()

    record = json.dumps({"body_hash": body_hash, "status_code": status_code, "body": body})
    # nx=True: if a concurrent request with the same key raced us and set
    # the record first, don't clobber theirs — both requests still executed
    # and returned a correct response; only the cached-for-replay copy is
    # decided by whoever won the race.
    await redis.set(key, record, ex=_TTL_SECONDS, nx=True)

    return IdempotentResult(status_code=status_code, body=body, replayed=False)
