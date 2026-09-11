from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from redis.asyncio import Redis, from_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    # Deliberately NOT app.core.db.get_session_factory() — that engine is a
    # process-level singleton cached across calls, which is correct for the
    # real app (one persistent event loop under uvicorn) but wrong here:
    # pytest-asyncio gives each test function its own event loop by default,
    # and an engine created in test A's loop breaks in test B's ("Event loop
    # is closed" / asyncpg AttributeError) once A's loop is torn down. Each
    # test gets its own engine, created and disposed inside its own loop.
    engine = create_async_engine(get_settings().database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True, scope="session")
def _requires_postgres() -> None:
    """Integration tests assume `docker compose -f infra/docker-compose.yml
    up -d` is already running and migrated to head — they are not run as
    part of the default `pytest` unit-only loop.
    """


_TRUNCATE_TABLES = text(
    """
    TRUNCATE
        identity.session,
        identity.principal,
        identity.account,
        governance.policy_decision,
        governance.kill_switch,
        governance.activation_record,
        governance.capability_status,
        governance.rights_grant,
        governance.rights_profile,
        reference.issuer,
        reference.instrument,
        market.source,
        market.accepted_fact,
        market.outbox_event,
        evidence.document,
        evidence.evidence_bundle,
        audit.event_log
    CASCADE
    """
)


async def _truncate_test_tables() -> None:
    # Admin (superuser) connection deliberately bypasses RLS/app-role
    # privileges for cleanup — a test that only cleans up "as itself" can't
    # reliably remove rows written under a different RLS context than the
    # one it ends on. Every table any integration test writes to belongs in
    # this list — add new ones here as new test modules land, or the next
    # test file rediscovers the same "leftover data across runs" bug that
    # test_rls_identity.py found the hard way.
    admin_engine = create_async_engine(get_settings().admin_database_url)
    async with admin_engine.begin() as conn:
        await conn.execute(_TRUNCATE_TABLES)
    await admin_engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_test_tables() -> AsyncIterator[None]:
    """Truncates every table integration tests write to, before AND after
    each test. Runs against a persistent dev database (not a fresh-per-run
    CI DB), so idempotency here isn't optional — the first run of
    test_rls_identity.py without this fixture failed on its second run with
    a UniqueViolationError on identity.principal.email, exactly because of
    this.
    """
    await _truncate_test_tables()
    yield
    await _truncate_test_tables()


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    # Same event-loop lesson as db_session: a fresh client per test, not
    # app.core.redis_client's cached singleton.
    client = from_url(get_settings().redis_url, decode_responses=True)
    yield client
    # Scoped delete-by-pattern, not FLUSHDB — Redis is shared infra and
    # nothing guarantees it stays idempotency-only forever (caching,
    # sessions may land here later).
    async for key in client.scan_iter("idempotency:*"):
        await client.delete(key)
    await client.aclose()
