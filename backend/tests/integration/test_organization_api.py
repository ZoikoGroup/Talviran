"""Organization member management over HTTP (G10, 2026-11-15 UAT gap
analysis): the role/seat-revocation-mid-session half of "test ... revoked
roles" that hadn't been covered by any existing test - this file had no
tests for app/modules/api/v1/organization.py at all before this.

Mirrors test_alerts_api.py's make_client/_signed_in pattern (own
engine/per-test-event-loop reasoning), plus test_auth_flow.py's redis
override + rate-limit-key clearing, since this file is the first one in
tests/integration to need both GET/DELETE-style client cookies *and* a real
POST /api/v1/auth/login round trip in the same test.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import get_session
from app.core.uuid7 import new_uuid7
from app.main import app
from app.modules.identity import service as identity_service
from app.modules.identity import supabase_auth
from app.modules.identity.models import Principal

PASSWORD = "correct-horse-9"


def _email(prefix: str = "org") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


ClientFactory = Callable[[], AbstractAsyncContextManager[AsyncClient]]


@pytest_asyncio.fixture
async def make_client(supabase_http: AsyncClient) -> AsyncIterator[ClientFactory]:
    from app.modules.api.v1 import auth as auth_module

    settings = get_settings()
    engine = create_async_engine(settings.test_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    redis_client: Redis = redis_from_url(settings.redis_url, decode_responses=True)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[auth_module._http] = lambda: supabase_http
    app.dependency_overrides[auth_module._redis] = lambda: redis_client

    # Rate-limit counters are keyed by (email, client IP), and every client
    # built off this one ASGI transport shares the same address - without
    # this, an earlier test in the same run can make this one's /login call
    # fail with 429 for reasons that have nothing to do with it (see
    # test_auth_flow.py's `client` fixture, same reasoning).
    async for rkey in redis_client.scan_iter("auth:attempts:*"):
        await redis_client.delete(rkey)

    @asynccontextmanager
    async def _client() -> AsyncIterator[AsyncClient]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    yield _client

    app.dependency_overrides.clear()
    await engine.dispose()
    await redis_client.aclose()


async def _signed_in(client: AsyncClient, email: str | None = None) -> str:
    address = email or _email()
    r = await client.post("/api/v1/auth/signup", json={"email": address, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return address


async def _add_member_to_account(
    db_session: AsyncSession,
    supabase_http: AsyncClient,
    *,
    account_id: uuid.UUID,
    admin_principal_id: uuid.UUID,
    role: str = "analyst",
) -> tuple[uuid.UUID, str]:
    """Adds a second, already-ACTIVE principal to `account_id` directly,
    mirroring exactly what organization.accept_invitation does (new
    Supabase user + new local Principal row with the target account_id and
    role) without going through that endpoint itself - accept_invitation
    calls app.core.http_client.get_http_client() as a plain function rather
    than through FastAPI DI, so it can't be pointed at FakeSupabaseAuth from
    a test the way every other auth-touching endpoint in this codebase can.
    Everything this test actually cares about - an active session in
    account_id, then that account's admin removing it - is unaffected by
    skipping the invitation-token bookkeeping itself.
    """
    member_email = _email("member")
    sb_user = await supabase_auth.sign_up(
        supabase_http, email=member_email, password=PASSWORD, settings=get_settings()
    )
    # identity.principal is FORCE RLS, account_id-scoped (migration 0002) -
    # the insert's WITH CHECK needs the GUC set to account_id *before* it
    # runs, same as _create_local_principal does for its own insert.
    await identity_service.apply_rls_context(
        db_session, account_id=account_id, principal_id=admin_principal_id
    )
    member_id = new_uuid7()
    db_session.add(
        Principal(
            id=member_id,
            account_id=account_id,
            email=member_email,
            status="ACTIVE",
            supabase_user_id=sb_user.id,
            role=role,
        )
    )
    await db_session.commit()
    return member_id, member_email


async def test_removing_a_member_mid_session_denies_their_very_next_request(
    make_client: ClientFactory, db_session: AsyncSession, supabase_http: AsyncClient
) -> None:
    """The second half of G10's "revoked roles" requirement: not just that a
    removed member's *next login* fails, but that a session they were
    already holding when the admin removed them is denied on its *very next
    request* - no separate session-revocation sweep needed, because
    identity.service.resolve_session re-checks both revoked_at and
    principal_status == "ACTIVE" from the database on every single call, and
    organization.remove_member both soft-deletes the principal (status ->
    REMOVED) and revokes every active identity.session row for them in the
    same transaction.
    """
    async with make_client() as admin_client:
        admin_email = await _signed_in(admin_client)
        me = await admin_client.get("/api/v1/auth/me")
        assert me.status_code == 200, me.text
        account_id = uuid.UUID(me.json()["account_id"])
        admin_principal_id = uuid.UUID(me.json()["principal_id"])
        assert me.json()["email"] == admin_email

        member_id, member_email = await _add_member_to_account(
            db_session,
            supabase_http,
            account_id=account_id,
            admin_principal_id=admin_principal_id,
        )

        async with make_client() as member_client:
            login = await member_client.post(
                "/api/v1/auth/login",
                json={"email": member_email, "password": PASSWORD},
            )
            assert login.status_code == 200, login.text
            assert uuid.UUID(login.json()["account_id"]) == account_id

            # The session is genuinely live before removal.
            before = await member_client.get("/api/v1/auth/me")
            assert before.status_code == 200, before.text

            removed = await admin_client.delete(f"/api/v1/organization/members/{member_id}")
            assert removed.status_code == 204, removed.text

            # No re-login attempt here at all - this is the literal next
            # request on the cookie the member already had.
            after = await member_client.get("/api/v1/auth/me")
            assert after.status_code == 401, (
                "a removed member's already-established session must be "
                "denied on its very next request, not merely on a future "
                f"login attempt: {after.text}"
            )

            # And the seat really is gone from the admin's own view, not
            # just soft-denied at the session layer.
            overview = await admin_client.get("/api/v1/organization")
            assert overview.status_code == 200, overview.text
            member_ids = {m["id"] for m in overview.json()["members"]}
            assert str(member_id) not in member_ids


async def test_non_admin_cannot_remove_a_member(
    make_client: ClientFactory, db_session: AsyncSession, supabase_http: AsyncClient
) -> None:
    """RBAC proof, not just isolation: a signed-in member of the *same*
    account who isn't an admin must not be able to remove a teammate, even
    though both principals share one account_id and RLS alone would happily
    let the row through.
    """
    async with make_client() as admin_client:
        await _signed_in(admin_client)
        me = await admin_client.get("/api/v1/auth/me")
        account_id = uuid.UUID(me.json()["account_id"])
        admin_principal_id = uuid.UUID(me.json()["principal_id"])

        analyst_id, analyst_email = await _add_member_to_account(
            db_session,
            supabase_http,
            account_id=account_id,
            admin_principal_id=admin_principal_id,
            role="analyst",
        )
        target_id, _ = await _add_member_to_account(
            db_session,
            supabase_http,
            account_id=account_id,
            admin_principal_id=admin_principal_id,
            role="viewer",
        )

        async with make_client() as analyst_client:
            login = await analyst_client.post(
                "/api/v1/auth/login",
                json={"email": analyst_email, "password": PASSWORD},
            )
            assert login.status_code == 200, login.text

            denied = await analyst_client.delete(f"/api/v1/organization/members/{target_id}")
            assert denied.status_code == 403, denied.text

        # The intended target is unaffected by the denied attempt.
        overview = await admin_client.get("/api/v1/organization")
        member_ids = {m["id"] for m in overview.json()["members"]}
        assert str(target_id) in member_ids


async def test_cannot_remove_a_member_of_another_account(
    make_client: ClientFactory, db_session: AsyncSession, supabase_http: AsyncClient
) -> None:
    """Cross-tenant proof: account A's admin cannot remove a principal who
    belongs to account B at all - the lookup in remove_member filters on
    Principal.account_id == identity.account_id explicitly (belt), and RLS
    would also hide the row even if that filter were ever dropped (braces).
    """
    async with make_client() as admin_a, make_client() as admin_b:
        await _signed_in(admin_a)
        me_a = await admin_a.get("/api/v1/auth/me")
        account_a = uuid.UUID(me_a.json()["account_id"])

        await _signed_in(admin_b)
        me_b = await admin_b.get("/api/v1/auth/me")
        account_b = uuid.UUID(me_b.json()["account_id"])
        principal_b = uuid.UUID(me_b.json()["principal_id"])
        assert account_a != account_b

        denied = await admin_a.delete(f"/api/v1/organization/members/{principal_b}")
        assert denied.status_code == 404, denied.text

        # B is still an active member of their own account.
        still_there = await admin_b.get("/api/v1/auth/me")
        assert still_there.status_code == 200, still_there.text
