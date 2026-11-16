"""POST/GET /api/v1/research/jobs and its /cancel sibling (UAT gap-
analysis G15) over real HTTP: idempotent creation, cross-tenant isolation,
and a cancel request that is itself idempotent - never an error, whatever
state the job is actually in.

Mirrors test_research_endpoint.py's make_client/_signed_in/_new_chat
pattern (self-contained per file by this codebase's own convention,
same reasoning that file's own docstring gives).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.asyncio import from_url as redis_from_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import get_session
from app.core.redis_client import get_redis
from app.main import app
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.research.crypto import DEK_BYTES, LocalKeyWrapper

PASSWORD = "correct-horse-9"
TEST_WRAPPER = LocalKeyWrapper(b"\x55" * DEK_BYTES, key_name="test/research-jobs-api")


def _email() -> str:
    return f"research-jobs-{uuid.uuid4().hex[:12]}@example.com"


ClientFactory = Callable[[], AbstractAsyncContextManager[AsyncClient]]


@pytest_asyncio.fixture
async def make_client(supabase_http: AsyncClient) -> AsyncIterator[ClientFactory]:
    from app.modules.api.v1 import auth as auth_module
    from app.modules.api.v1 import deps

    settings = get_settings()
    engine = create_async_engine(settings.test_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = redis_from_url(settings.redis_url, decode_responses=True)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[deps.key_wrapper] = lambda: TEST_WRAPPER
    app.dependency_overrides[get_redis] = lambda: redis_client
    app.dependency_overrides[auth_module._http] = lambda: supabase_http

    @asynccontextmanager
    async def _client() -> AsyncIterator[AsyncClient]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    yield _client

    app.dependency_overrides.clear()
    await engine.dispose()
    await redis_client.aclose()


async def _signed_in(client: AsyncClient) -> str:
    email = _email()
    r = await client.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return email


async def _new_chat(client: AsyncClient) -> str:
    r = await client.post("/api/v1/chats", json={"model": "talvrin-pro", "title": "Gilts"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _seed_pdp_prerequisites(db_session: AsyncSession) -> None:
    db_session.add(
        CapabilityStatus(
            capability_code="research.answer", jurisdiction_code=None, status="AVAILABLE"
        )
    )
    db_session.add(
        ActivationRecord(
            jurisdiction_code="GB", operating_entity="Test Entity", status="ACTIVE",
            effective_from=dt.datetime.now(dt.UTC) - dt.timedelta(days=1), effective_to=None,
        )
    )
    await db_session.commit()


async def test_create_job_is_queued_with_no_worker_running(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as client:
        await _signed_in(client)
        chat_id = await _new_chat(client)

        r = await client.post(
            "/api/v1/research/jobs",
            json={"conversation_id": chat_id, "query": "should I buy this gilt?"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "QUEUED"
        assert body["result"] is None
        assert body["error"] is None

        got = await client.get(f"/api/v1/research/jobs/{body['job_id']}")
        assert got.status_code == 200
        assert got.json()["status"] == "QUEUED"


async def test_repeating_the_same_idempotency_key_returns_the_same_job(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as client:
        await _signed_in(client)
        chat_id = await _new_chat(client)
        key = str(uuid.uuid4())
        payload = {"conversation_id": chat_id, "query": "should I buy this gilt?"}

        first = await client.post(
            "/api/v1/research/jobs", json=payload, headers={"Idempotency-Key": key}
        )
        second = await client.post(
            "/api/v1/research/jobs", json=payload, headers={"Idempotency-Key": key}
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["job_id"] == second.json()["job_id"]


async def test_missing_idempotency_key_is_rejected(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as client:
        await _signed_in(client)
        chat_id = await _new_chat(client)
        r = await client.post(
            "/api/v1/research/jobs",
            json={"conversation_id": chat_id, "query": "hello"},
        )
        assert r.status_code == 422


async def test_another_signed_in_user_cannot_read_someone_elses_job(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as owner, make_client() as other:
        await _signed_in(owner)
        chat_id = await _new_chat(owner)
        created = await owner.post(
            "/api/v1/research/jobs",
            json={"conversation_id": chat_id, "query": "should I buy this gilt?"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        job_id = created.json()["job_id"]

        await _signed_in(other)
        denied = await other.get(f"/api/v1/research/jobs/{job_id}")
        assert denied.status_code == 404


async def test_canceling_a_queued_job_sets_cancel_requested_and_is_idempotent(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as client:
        await _signed_in(client)
        chat_id = await _new_chat(client)
        created = await client.post(
            "/api/v1/research/jobs",
            json={"conversation_id": chat_id, "query": "should I buy this gilt?"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        job_id = created.json()["job_id"]

        first_cancel = await client.post(f"/api/v1/research/jobs/{job_id}/cancel")
        assert first_cancel.status_code == 200
        assert first_cancel.json()["status"] == "CANCEL_REQUESTED"

        # Idempotent: cancelling an already-cancel-requested job is not an
        # error and does not change anything further.
        second_cancel = await client.post(f"/api/v1/research/jobs/{job_id}/cancel")
        assert second_cancel.status_code == 200
        assert second_cancel.json()["status"] == "CANCEL_REQUESTED"


async def test_canceling_an_unknown_job_is_not_found(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as client:
        await _signed_in(client)
        r = await client.post(f"/api/v1/research/jobs/{uuid.uuid4()}/cancel")
        assert r.status_code == 404
