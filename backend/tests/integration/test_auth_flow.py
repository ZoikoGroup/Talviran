"""End-to-end auth against the real database (SEC-001 §7–§9).

These exercise the HTTP surface rather than the service functions, because
the parts most likely to break in production live in the wiring: cookie
flags, RLS context on a pooled connection, and what a failure discloses.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from redis.asyncio import Redis, from_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.db import get_session
from app.main import app
from app.modules.api.v1.auth import _redis
from app.modules.identity.cookies import SESSION_COOKIE_NAME
from app.modules.identity.tokens import hash_token

PASSWORD = "correct-horse-9"


def _email() -> str:
    return f"auth-{uuid.uuid4().hex[:12]}@example.com"


def _session_token(client: AsyncClient) -> str:
    """The session cookie, asserted present.

    Reading it straight from the jar gives `str | None`; letting a None
    through would make the assertions below vacuous rather than failing.
    """
    token = client.cookies.get(SESSION_COOKIE_NAME)
    assert token is not None, "expected a session cookie to have been set"
    return token


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """A client whose engine and Redis connection belong to *this* test's loop.

    app.core.db and app.core.redis_client both cache a process-level
    singleton, which is right under uvicorn's single persistent loop and wrong
    here: pytest-asyncio gives every test its own loop, so a connection opened
    in one test is unusable in the next ("Event loop is closed"). Overriding
    the dependencies is cleaner than resetting the module globals, because it
    leaves the production wiring untouched.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    redis: Redis = from_url(settings.redis_url, decode_responses=True)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[_redis] = lambda: redis

    # Rate-limit counters are keyed by IP, and every test shares the ASGI
    # client's address — without this, earlier tests exhaust the budget and
    # later ones fail with 429 for reasons that have nothing to do with them.
    async for key in redis.scan_iter("auth:attempts:*"):
        await redis.delete(key)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
    await redis.aclose()
    await engine.dispose()


async def _signup(
    client: AsyncClient, email: str, password: str = PASSWORD
) -> Response:
    return await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": password}
    )


# ---------------------------------------------------------------- sign up


async def test_signup_creates_an_account_and_signs_in(client: AsyncClient) -> None:
    email = _email()
    r = await _signup(client, email)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == email
    assert uuid.UUID(body["principal_id"])
    assert uuid.UUID(body["account_id"])
    assert client.cookies.get(SESSION_COOKIE_NAME)


async def test_signup_rejects_a_weak_password(client: AsyncClient) -> None:
    r = await _signup(client, _email(), "short")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_signup_rejects_a_duplicate_email(client: AsyncClient) -> None:
    email = _email()
    assert (await _signup(client, email)).status_code == 201
    again = await _signup(client, email)
    assert again.status_code == 409


async def test_email_uniqueness_ignores_case(client: AsyncClient) -> None:
    """Otherwise Shiva@… and shiva@… become two accounts and sign-in becomes
    ambiguous."""
    email = _email()
    assert (await _signup(client, email)).status_code == 201
    again = await _signup(client, email.upper())
    assert again.status_code == 409


# ---------------------------------------------------------------- sign in


async def test_login_with_correct_credentials(client: AsyncClient) -> None:
    email = _email()
    await _signup(client, email)
    client.cookies.clear()

    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert r.status_code == 200
    assert r.json()["email"] == email
    assert client.cookies.get(SESSION_COOKIE_NAME)


async def test_login_is_case_insensitive_on_email(client: AsyncClient) -> None:
    email = _email()
    await _signup(client, email)
    client.cookies.clear()
    r = await client.post(
        "/api/v1/auth/login", json={"email": email.upper(), "password": PASSWORD}
    )
    assert r.status_code == 200


async def test_wrong_password_is_rejected(client: AsyncClient) -> None:
    email = _email()
    await _signup(client, email)
    client.cookies.clear()
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong-password-1"}
    )
    assert r.status_code == 401


async def test_failures_do_not_reveal_whether_an_account_exists(
    client: AsyncClient,
) -> None:
    """§7.1 no account enumeration — an unknown address and a wrong password
    must be indistinguishable in status and message."""
    known = _email()
    await _signup(client, known)
    client.cookies.clear()

    wrong_password = await client.post(
        "/api/v1/auth/login", json={"email": known, "password": "wrong-password-1"}
    )
    unknown_address = await client.post(
        "/api/v1/auth/login", json={"email": _email(), "password": "wrong-password-1"}
    )

    assert wrong_password.status_code == unknown_address.status_code == 401
    assert (
        wrong_password.json()["error"]["message"]
        == unknown_address.json()["error"]["message"]
    )


async def test_a_failed_login_sets_no_cookie(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"email": _email(), "password": "wrong-password-1"}
    )
    assert r.status_code == 401
    assert SESSION_COOKIE_NAME not in r.cookies


# ---------------------------------------------------------------- cookie


async def test_session_cookie_carries_the_required_flags(client: AsyncClient) -> None:
    r = await _signup(client, _email())
    header = r.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    assert "Path=/" in header


async def test_the_database_never_stores_the_usable_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The point of §8's design: a dump of identity.session must not contain
    anything that can authenticate a request.

    Queried through the lookup function rather than a plain SELECT. RLS hides
    identity.session from a connection with no principal context, so a direct
    `SELECT ... WHERE token_hash = :t` returns zero rows whatever the value is
    — it would pass while proving nothing.
    """
    await _signup(client, _email())
    token = _session_token(client)

    by_raw_token = await db_session.execute(
        text("SELECT count(*) FROM identity.lookup_session_by_token(:t)"),
        {"t": token},
    )
    assert by_raw_token.scalar_one() == 0, "the raw token must not be a stored key"

    by_digest = await db_session.execute(
        text("SELECT count(*) FROM identity.lookup_session_by_token(:t)"),
        {"t": hash_token(token)},
    )
    assert by_digest.scalar_one() == 1, "the digest is what is stored"


# ---------------------------------------------------------------- me / logout


async def test_me_returns_the_signed_in_principal(client: AsyncClient) -> None:
    email = _email()
    await _signup(client, email)
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == email


async def test_me_without_a_cookie_is_unauthenticated(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_a_forged_token_is_rejected(client: AsyncClient) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, "not-a-real-token")
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_logout_revokes_the_session_server_side(client: AsyncClient) -> None:
    """Clearing the cookie is not enough — a copied token must stop working,
    which is why sessions are rows rather than signed tokens."""
    await _signup(client, _email())
    stolen = _session_token(client)

    assert (await client.post("/api/v1/auth/logout")).status_code == 204

    client.cookies.set(SESSION_COOKIE_NAME, stolen)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_logout_without_a_session_is_not_an_error(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/logout")).status_code == 204


# ---------------------------------------------------------------- isolation


async def test_two_accounts_are_isolated(client: AsyncClient) -> None:
    first = _email()
    await _signup(client, first)
    first_account = (await client.get("/api/v1/auth/me")).json()["account_id"]

    client.cookies.clear()
    second = _email()
    await _signup(client, second)
    second_account = (await client.get("/api/v1/auth/me")).json()["account_id"]

    assert first_account != second_account


async def test_rls_still_blocks_direct_reads_without_context(
    db_session: AsyncSession,
) -> None:
    """The definer functions must be the only way through — a plain select on
    a fresh transaction must see nothing."""
    count = await db_session.execute(text("SELECT count(*) FROM identity.principal"))
    assert count.scalar_one() == 0


# ---------------------------------------------------------------- rate limit


@pytest.mark.parametrize("attempts", [12])
async def test_repeated_failures_are_rate_limited(
    client: AsyncClient, attempts: int
) -> None:
    """§7.1 brute-force control. The limit applies to unknown addresses too,
    so it cannot itself become an account-existence oracle."""
    email = _email()
    statuses = []
    for _ in range(attempts):
        r = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password-1"}
        )
        statuses.append(r.status_code)

    assert 429 in statuses, statuses
    assert statuses.index(429) > 0, "should not block the very first attempt"
