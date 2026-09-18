"""The research endpoints over HTTP, with two real signed-in users.

test_research_isolation.py proves the database boundary. This file proves the
boundary a customer actually meets: two browsers, two cookies, one trying to
read the other's conversation by its identifier.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.db import get_session
from app.main import app
from app.modules.research.crypto import DEK_BYTES, LocalKeyWrapper

PASSWORD = "correct-horse-9"

#: Overrides the configured wrapper so the suite does not depend on the
#: environment's key material.
TEST_WRAPPER = LocalKeyWrapper(b"\x22" * DEK_BYTES, key_name="test/api")


def _email() -> str:
    return f"api-{uuid.uuid4().hex[:12]}@example.com"


ClientFactory = Callable[[], AbstractAsyncContextManager[AsyncClient]]


@pytest_asyncio.fixture
async def make_client(supabase_http: AsyncClient) -> AsyncIterator[ClientFactory]:
    """Hands out independent clients, each with its own cookie jar.

    Same per-test engine reasoning as the auth suite: the process-level
    singletons in app.core.db belong to uvicorn's single loop, not to
    pytest-asyncio's per-test loops. Every client made by the returned
    factory shares one FakeSupabaseAuth-backed `_http` override, since they
    all belong to the same test regardless of how many separate "users"
    (alice, bob, ...) sign up through it.
    """
    from app.modules.api.v1 import auth as auth_module
    from app.modules.api.v1 import deps

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[deps.key_wrapper] = lambda: TEST_WRAPPER
    app.dependency_overrides[auth_module._http] = lambda: supabase_http

    @asynccontextmanager
    async def _client() -> AsyncIterator[AsyncClient]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    yield _client

    app.dependency_overrides.clear()
    await engine.dispose()


async def _signed_in(client: AsyncClient) -> str:
    email = _email()
    r = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": PASSWORD}
    )
    assert r.status_code == 201, r.text
    return email


async def _new_chat(client: AsyncClient, title: str = "Gilts") -> str:
    r = await client.post(
        "/api/v1/chats", json={"model": "talvrin-pro", "title": title}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


# ------------------------------------------------------------ the basics


async def test_a_chat_round_trips(make_client: ClientFactory) -> None:
    async with make_client() as client:
        await _signed_in(client)
        chat_id = await _new_chat(client)

        posted = await client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "What is the 10y gilt yield?"},
        )
        assert posted.status_code == 201

        got = await client.get(f"/api/v1/chats/{chat_id}")
        assert got.status_code == 200
        body = got.json()
        assert body["title"] == "Gilts"
        assert [m["content"] for m in body["messages"]] == [
            "What is the 10y gilt yield?"
        ]


async def test_chats_require_a_session(make_client: ClientFactory) -> None:
    async with make_client() as client:
        assert (await client.get("/api/v1/chats")).status_code == 401
        assert (await client.post("/api/v1/chats", json={})).status_code == 401


async def test_an_unknown_model_is_rejected(make_client: ClientFactory) -> None:
    async with make_client() as client:
        await _signed_in(client)
        r = await client.post(
            "/api/v1/chats", json={"model": "gpt-4", "title": "nope"}
        )
        assert r.status_code == 422


# ----------------------------------------------------- one user vs another


async def test_another_signed_in_user_cannot_read_the_chat(
    make_client: ClientFactory,
) -> None:
    async with make_client() as alice:
        await _signed_in(alice)
        chat_id = await _new_chat(alice, "Alice private")
        await alice.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "secret position"},
        )

        async with make_client() as bob:
            await _signed_in(bob)
            assert (await bob.get(f"/api/v1/chats/{chat_id}")).status_code == 404
            assert bob.get is not None
            listed = await bob.get("/api/v1/chats")
            assert listed.json() == []


async def test_another_signed_in_user_cannot_write_to_the_chat(
    make_client: ClientFactory,
) -> None:
    async with make_client() as alice:
        await _signed_in(alice)
        chat_id = await _new_chat(alice)

        async with make_client() as bob:
            await _signed_in(bob)
            injected = await bob.post(
                f"/api/v1/chats/{chat_id}/messages",
                json={"content": "injected"},
            )
            assert injected.status_code == 404

            renamed = await bob.patch(
                f"/api/v1/chats/{chat_id}", json={"title": "hijacked"}
            )
            assert renamed.status_code == 404

            deleted = await bob.delete(f"/api/v1/chats/{chat_id}")
            assert deleted.status_code == 404

        # Untouched.
        body = (await alice.get(f"/api/v1/chats/{chat_id}")).json()
        assert body["title"] == "Gilts"
        assert body["messages"] == []


async def test_a_missing_chat_and_a_foreign_chat_look_identical(
    make_client: ClientFactory,
) -> None:
    """Otherwise the API becomes an oracle for which identifiers exist."""
    async with make_client() as alice:
        await _signed_in(alice)
        real = await _new_chat(alice)

        async with make_client() as bob:
            await _signed_in(bob)
            foreign = await bob.get(f"/api/v1/chats/{real}")
            absent = await bob.get(f"/api/v1/chats/{uuid.uuid4()}")
            assert foreign.status_code == absent.status_code == 404

            # request_id differs per call by design, so compare what a caller
            # could actually learn from: the code and the wording.
            def _disclosed(response: object) -> tuple[str, str]:
                error = response.json()["error"]  # type: ignore[attr-defined]
                return error["code"], error["message"]

            assert _disclosed(foreign) == _disclosed(absent)


# ---------------------------------------------------------------- sharing


async def test_a_share_link_is_readable_without_signing_in(
    make_client: ClientFactory,
) -> None:
    async with make_client() as alice:
        await _signed_in(alice)
        chat_id = await _new_chat(alice, "Public thesis")
        await alice.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "Shareable question"},
        )
        share = await alice.post(f"/api/v1/chats/{chat_id}/share", json={})
        assert share.status_code == 201
        token = share.json()["token"]

    # A brand-new client with no cookies at all.
    async with make_client() as anonymous:
        view = await anonymous.get(f"/api/v1/shared/{token}")
        assert view.status_code == 200
        body = view.json()
        assert body["title"] == "Public thesis"
        assert [m["content"] for m in body["messages"]] == ["Shareable question"]
        # The viewer learns nothing about who owns it.
        assert "account_id" not in body
        assert "principal_id" not in body


async def test_a_share_link_does_not_unlock_the_rest_of_the_account(
    make_client: ClientFactory,
) -> None:
    async with make_client() as alice:
        await _signed_in(alice)
        shared_id = await _new_chat(alice, "Shared")
        other_id = await _new_chat(alice, "Not shared")
        share = await alice.post(f"/api/v1/chats/{shared_id}/share", json={})
        token = share.json()["token"]

    async with make_client() as anonymous:
        assert (await anonymous.get(f"/api/v1/shared/{token}")).status_code == 200
        # Holding a link is not a session.
        assert (await anonymous.get("/api/v1/chats")).status_code == 401
        assert (await anonymous.get(f"/api/v1/chats/{other_id}")).status_code == 401


async def test_a_revoked_link_stops_working(make_client: ClientFactory) -> None:
    async with make_client() as alice:
        await _signed_in(alice)
        chat_id = await _new_chat(alice)
        share = (await alice.post(f"/api/v1/chats/{chat_id}/share", json={})).json()

        async with make_client() as anonymous:
            assert (
                await anonymous.get(f"/api/v1/shared/{share['token']}")
            ).status_code == 200

        assert (
            await alice.delete(f"/api/v1/shares/{share['id']}")
        ).status_code == 204

        async with make_client() as anonymous:
            assert (
                await anonymous.get(f"/api/v1/shared/{share['token']}")
            ).status_code == 404


async def test_a_stranger_cannot_revoke_someone_elses_link(
    make_client: ClientFactory,
) -> None:
    async with make_client() as alice:
        await _signed_in(alice)
        chat_id = await _new_chat(alice)
        share = (await alice.post(f"/api/v1/chats/{chat_id}/share", json={})).json()

        async with make_client() as bob:
            await _signed_in(bob)
            assert (
                await bob.delete(f"/api/v1/shares/{share['id']}")
            ).status_code == 404

        async with make_client() as anonymous:
            assert (
                await anonymous.get(f"/api/v1/shared/{share['token']}")
            ).status_code == 200


async def test_a_forged_share_token_is_rejected(
    make_client: ClientFactory,
) -> None:
    async with make_client() as anonymous:
        r = await anonymous.get("/api/v1/shared/not-a-real-token")
        assert r.status_code == 404


# --------------------------------------------------------------- projects


async def test_projects_are_private_to_their_account(
    make_client: ClientFactory,
) -> None:
    async with make_client() as alice:
        await _signed_in(alice)
        created = await alice.post(
            "/api/v1/projects", json={"name": "Sovereign debt"}
        )
        assert created.status_code == 201
        project_id = created.json()["id"]

        async with make_client() as bob:
            await _signed_in(bob)
            assert (await bob.get("/api/v1/projects")).json() == []
            assert (
                await bob.patch(
                    f"/api/v1/projects/{project_id}", json={"name": "taken"}
                )
            ).status_code == 404
            # Filing your own chat into someone else's project is refused.
            assert (
                await bob.post(
                    "/api/v1/chats",
                    json={"model": "talvrin-go", "project_id": project_id},
                )
            ).status_code == 404
