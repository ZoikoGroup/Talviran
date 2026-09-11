"""Proves run_idempotent's actual behavior against real Redis, not a mock —
the two things that matter most: the handler runs exactly once per key,
and a body mismatch on a reused key is a hard conflict, never a silent
overwrite (the tempting wrong-first-draft this exists to prevent).
"""

import uuid

import pytest
from redis.asyncio import Redis

from app.core.idempotency import IdempotencyConflictError, run_idempotent


async def test_first_call_executes_handler_and_returns_fresh_result(
    redis_client: Redis,
) -> None:
    calls = 0

    async def handler() -> tuple[int, dict[str, str]]:
        nonlocal calls
        calls += 1
        return 201, {"created": "yes"}

    result = await run_idempotent(
        redis_client,
        scope="test.scope",
        idempotency_key=str(uuid.uuid4()),
        request_body=b'{"a":1}',
        handler=handler,
    )

    assert calls == 1
    assert result.replayed is False
    assert result.status_code == 201
    assert result.body == {"created": "yes"}


async def test_same_key_same_body_replays_without_recalling_handler(
    redis_client: Redis,
) -> None:
    calls = 0
    key = str(uuid.uuid4())

    async def handler() -> tuple[int, dict[str, str]]:
        nonlocal calls
        calls += 1
        return 201, {"created": "yes"}

    first = await run_idempotent(
        redis_client,
        scope="test.scope",
        idempotency_key=key,
        request_body=b'{"a":1}',
        handler=handler,
    )
    second = await run_idempotent(
        redis_client,
        scope="test.scope",
        idempotency_key=key,
        request_body=b'{"a":1}',
        handler=handler,
    )

    assert calls == 1, "handler must not run twice for the same key+body"
    assert first.replayed is False
    assert second.replayed is True
    assert second.status_code == first.status_code
    assert second.body == first.body


async def test_same_key_different_body_raises_conflict(redis_client: Redis) -> None:
    key = str(uuid.uuid4())

    async def handler() -> tuple[int, dict[str, str]]:
        return 201, {"created": "yes"}

    await run_idempotent(
        redis_client,
        scope="test.scope",
        idempotency_key=key,
        request_body=b'{"a":1}',
        handler=handler,
    )

    with pytest.raises(IdempotencyConflictError):
        await run_idempotent(
            redis_client,
            scope="test.scope",
            idempotency_key=key,
            request_body=b'{"a":2}',  # different body, same key
            handler=handler,
        )


async def test_different_scope_does_not_collide_on_same_key(redis_client: Redis) -> None:
    # Two different endpoints happening to receive the same client-chosen
    # key must not see each other's cached response.
    key = str(uuid.uuid4())

    async def handler_a() -> tuple[int, dict[str, str]]:
        return 200, {"from": "a"}

    async def handler_b() -> tuple[int, dict[str, str]]:
        return 200, {"from": "b"}

    result_a = await run_idempotent(
        redis_client, scope="scope.a", idempotency_key=key, request_body=b"{}", handler=handler_a
    )
    result_b = await run_idempotent(
        redis_client, scope="scope.b", idempotency_key=key, request_body=b"{}", handler=handler_b
    )

    assert result_a.body == {"from": "a"}
    assert result_b.body == {"from": "b"}
    assert result_b.replayed is False
