import json
import uuid
from collections.abc import AsyncIterator

import httpx
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
        research.conversation_share,
        research.message,
        research.conversation,
        research.project,
        research.account_data_key,
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
        calculation.calculation_specification,
        calculation.calculation_result,
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


class FakeSupabaseAuth:
    """In-memory stand-in for the three GoTrue endpoints identity/supabase_auth.py
    calls, shaped from what the real project actually returns (confirmed
    2026-09-16, see that module's docstring) rather than guessed:

      * /signup: the new user at the TOP level of the body, not nested; a
        duplicate email comes back 200 with `identities: []`, not a 4xx.
      * /token: `user` nested under that key; a rejected login is
        `error_code: invalid_credentials` regardless of which side was wrong.
      * /recover: 200 `{}` unconditionally.
      * PUT /user: the recovery token as a bearer; a bad one is
        `403 bad_jwt`, confirmed live against the real project — see
        identity/supabase_auth.py's InvalidResetToken docstring. Also
        confirmed live: the token is NOT single-use at Supabase's level — it
        is a normal access token, reusable for its full ~1 hour lifetime —
        so this fake stays reusable too, matching reality. Single-use is
        enforced one layer up, by this app's own Redis denylist
        (identity/reset_tokens.py), not by Supabase and not by this fake.

    Deliberately does not simulate email confirmation — this codebase runs
    with confirmation disabled (see supabase_auth.EmailNotConfirmed's
    docstring), so a fake that required it would be testing a mode the
    product doesn't run in.

    /recover doesn't send anything a test could intercept — there is no fake
    inbox here — so it also mints a one-time recovery token internally,
    exposed via `recovery_token_for()`, standing in for "the token a real
    user would get from the email link's URL fragment" (confirmed live: a
    real recovery link redirects to `#access_token=...&type=recovery`).
    """

    def __init__(self) -> None:
        self.users_by_email: dict[str, dict[str, str]] = {}
        self._recovery_tokens: dict[str, str] = {}

    async def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if request.method == "PUT" and path.endswith("/auth/v1/user"):
            return self._update_password(request)

        body = json.loads(request.content or b"{}")
        if path.endswith("/auth/v1/signup"):
            return self._signup(body)
        if path.endswith("/auth/v1/token"):
            return self._token(body)
        if path.endswith("/auth/v1/recover"):
            return self._recover(body)
        return httpx.Response(404, json={"msg": f"unhandled path {path}"})

    def _recover(self, body: dict[str, str]) -> httpx.Response:
        email = body["email"].strip().lower()
        # Real GoTrue answers identically whether or not the address has an
        # account — see supabase_auth.request_password_reset's docstring —
        # so a token is minted only for a known address, but the response
        # itself never says which case this was.
        if email in self.users_by_email:
            self._recovery_tokens[f"recovery-{uuid.uuid4().hex}"] = email
        return httpx.Response(200, json={})

    def recovery_token_for(self, email: str) -> str:
        """The token this fake minted for the most recent /recover call
        against `email` — tests use this exactly as a real page would use
        the access_token parsed from its URL fragment."""
        for token, owner in self._recovery_tokens.items():
            if owner == email.strip().lower():
                return token
        raise AssertionError(f"no recovery token was ever minted for {email!r}")

    def _update_password(self, request: httpx.Request) -> httpx.Response:
        bearer = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        email = self._recovery_tokens.get(bearer)
        if email is None:
            return httpx.Response(
                403,
                json={"code": 403, "error_code": "bad_jwt", "msg": "invalid JWT"},
            )
        body = json.loads(request.content or b"{}")
        new_password = body["password"]
        if len(new_password) < 6:
            return httpx.Response(
                422,
                json={
                    "code": 422,
                    "error_code": "weak_password",
                    "msg": "Password should be at least 6 characters.",
                },
            )
        # Deliberately NOT deleted here — see the class docstring. Reusing
        # this same token again must still succeed at this layer, so that
        # the single-use test actually exercises this app's own Redis
        # denylist rather than a stronger guarantee the fake invented.
        self.users_by_email[email]["password"] = new_password
        return httpx.Response(200, json={"id": self.users_by_email[email]["id"], "email": email})

    def _signup(self, body: dict[str, str]) -> httpx.Response:
        email = body["email"].strip().lower()
        password = body["password"]
        if len(password) < 6:
            return httpx.Response(
                422,
                json={
                    "code": 422,
                    "error_code": "weak_password",
                    "msg": "Password should be at least 6 characters.",
                },
            )
        existing = self.users_by_email.get(email)
        if existing is not None:
            # GoTrue's real signal for "already registered, confirmed
            # identity": 200, not 4xx, with no new identity created.
            return httpx.Response(
                200, json={"id": existing["id"], "email": email, "identities": []}
            )
        user_id = str(uuid.uuid4())
        self.users_by_email[email] = {"id": user_id, "password": password}
        return httpx.Response(
            200, json={"id": user_id, "email": email, "identities": [{"id": user_id}]}
        )

    def _token(self, body: dict[str, str]) -> httpx.Response:
        email = body["email"].strip().lower()
        password = body["password"]
        existing = self.users_by_email.get(email)
        if existing is None or existing["password"] != password:
            return httpx.Response(
                400,
                json={
                    "code": 400,
                    "error_code": "invalid_credentials",
                    "msg": "Invalid login credentials",
                },
            )
        return httpx.Response(
            200,
            json={
                "access_token": "fake-access-token",
                "token_type": "bearer",
                "user": {"id": existing["id"], "email": email},
            },
        )


@pytest.fixture
def fake_supabase() -> FakeSupabaseAuth:
    """A fresh in-memory user store per test — nothing here talks to the
    real Supabase project. Plain `pytest.fixture`, not `pytest_asyncio`: it
    does nothing async, and pytest-asyncio's stubs don't type-check a
    fixture whose body is neither a coroutine nor an async generator."""
    return FakeSupabaseAuth()


@pytest_asyncio.fixture
async def supabase_http(fake_supabase: FakeSupabaseAuth) -> AsyncIterator[httpx.AsyncClient]:
    """An httpx.AsyncClient that looks real to identity/supabase_auth.py but
    is backed by FakeSupabaseAuth's transport — pass this as the `http`
    argument to service.register/authenticate directly, or override
    app.modules.api.v1.auth._http with it for full-HTTP tests."""
    transport = httpx.MockTransport(fake_supabase.handler)
    async with httpx.AsyncClient(transport=transport) as client:
        yield client


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
