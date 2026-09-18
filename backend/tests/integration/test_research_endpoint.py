"""POST /api/v1/research over HTTP: a real signed-in user, a real chat, the
Idempotency-Key contract (replay on same key+body, 409 on same key+different
body), and that it's reachable at all only when signed in.

Mirrors test_research_api.py's make_client/_signed_in/_new_chat pattern
(same per-test-engine reasoning) rather than importing it cross-file, since
each test file here is self-contained by convention.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.asyncio import from_url as redis_from_url
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import get_session
from app.core.redis_client import get_redis
from app.main import app
from app.modules.evidence.service import SEED_GILT_ISIN
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.reference.models import Instrument, InstrumentAlias, Issuer
from app.modules.research.crypto import DEK_BYTES, LocalKeyWrapper
from app.modules.rights.models import RightsGrant, RightsProfile

PASSWORD = "correct-horse-9"
TEST_WRAPPER = LocalKeyWrapper(b"\x33" * DEK_BYTES, key_name="test/research-endpoint")


def _email() -> str:
    return f"research-{uuid.uuid4().hex[:12]}@example.com"


ClientFactory = Callable[[], AbstractAsyncContextManager[AsyncClient]]


@pytest_asyncio.fixture
async def make_client(supabase_http: AsyncClient) -> AsyncIterator[ClientFactory]:
    from app.modules.api.v1 import auth as auth_module
    from app.modules.api.v1 import deps

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    # get_redis() is the same process-level-singleton-bound-to-one-event-loop
    # pattern as app.core.db's engine (the Week 3 lesson) - a fresh client
    # per test, not the cached singleton, or the second test in a run hits
    # "Event loop is closed" against a connection from a torn-down loop.
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


async def test_research_round_trips_into_the_chat(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as client:
        await _signed_in(client)
        chat_id = await _new_chat(client)

        r = await client.post(
            "/api/v1/research",
            json={"conversation_id": chat_id, "query": "should I buy this gilt?"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert "can't tell you whether to buy" in body["text"]
        assert body["allowed_output_type"] == "NEUTRAL_EDUCATION"
        assert body["evidence_bundle_id"] is None

        got = await client.get(f"/api/v1/chats/{chat_id}")
        messages = got.json()["messages"]
        assert [m["role"] for m in messages] == ["USER", "ASSISTANT"]
        assert messages[0]["content"] == "should I buy this gilt?"
        assert messages[1]["content"] == body["text"]


async def test_replaying_the_same_idempotency_key_does_not_duplicate(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as client:
        await _signed_in(client)
        chat_id = await _new_chat(client)
        key = str(uuid.uuid4())
        payload = {"conversation_id": chat_id, "query": "what is accrued interest?"}

        first = await client.post(
            "/api/v1/research", json=payload, headers={"Idempotency-Key": key}
        )
        second = await client.post(
            "/api/v1/research", json=payload, headers={"Idempotency-Key": key}
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json() == second.json()

        got = await client.get(f"/api/v1/chats/{chat_id}")
        assert len(got.json()["messages"]) == 2, "a replay must not append a second turn"


async def test_same_key_different_body_is_a_conflict(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as client:
        await _signed_in(client)
        chat_id = await _new_chat(client)
        key = str(uuid.uuid4())

        first = await client.post(
            "/api/v1/research",
            json={"conversation_id": chat_id, "query": "what is accrued interest?"},
            headers={"Idempotency-Key": key},
        )
        second = await client.post(
            "/api/v1/research",
            json={"conversation_id": chat_id, "query": "a completely different question"},
            headers={"Idempotency-Key": key},
        )
        assert first.status_code == 201
        assert second.status_code == 409


async def test_missing_idempotency_key_is_rejected(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as client:
        await _signed_in(client)
        chat_id = await _new_chat(client)
        r = await client.post(
            "/api/v1/research", json={"conversation_id": chat_id, "query": "hello"}
        )
        assert r.status_code == 422


async def test_research_requires_a_session(make_client: ClientFactory) -> None:
    async with make_client() as client:
        r = await client.post(
            "/api/v1/research",
            json={"conversation_id": str(uuid.uuid4()), "query": "hello"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 401


async def test_unknown_conversation_is_not_found(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as client:
        await _signed_in(client)
        r = await client.post(
            "/api/v1/research",
            json={"conversation_id": str(uuid.uuid4()), "query": "hello"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------- GET evidence


async def _seed_gilt_evidence_data(session: AsyncSession) -> None:
    issuer = Issuer(name="HM Treasury", country_code="GB", status="ACTIVE")
    session.add(issuer)
    await session.flush()
    instrument = Instrument(
        issuer_id=issuer.id, instrument_type="FI_SOVEREIGN",
        name="4 1/4% Treasury Stock 2036", currency_code="GBP", status="ACTIVE",
    )
    session.add(instrument)
    await session.flush()
    session.add(
        InstrumentAlias(instrument_id=instrument.id, alias_type="ISIN", alias_value=SEED_GILT_ISIN)
    )
    session.add(
        AcceptedFact(
            subject_type="INSTRUMENT", subject_id=instrument.id,
            metric_id=METRIC_GILT_REFERENCE_TERMS,
            valid_range=Range(
                lower=dt.datetime(2003, 2, 27, tzinfo=dt.UTC), upper=None, bounds="[)"
            ),
            knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
            value={
                "instrument_name": "4 1/4% Treasury Stock 2036", "gilt_type": "CONVENTIONAL",
                "coupon_rate": "4.25", "redemption_date": "2036-03-07",
                "first_issue_date": "2003-02-27", "dividend_dates": "07-Mar and 07-Sep",
            },
            status="ACTIVE",
        )
    )
    profile = RightsProfile(code="uk-dmo.gilts", status="ACTIVE")
    session.add(profile)
    await session.flush()
    session.add(
        RightsGrant(rights_profile_id=profile.id, action="display", permission_state="ALLOW")
    )
    await session.commit()


async def test_evidence_is_retrievable_for_a_facts_backed_reply(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    await _seed_gilt_evidence_data(db_session)
    async with make_client() as client:
        await _signed_in(client)
        chat_id = await _new_chat(client)

        posted = await client.post(
            "/api/v1/research",
            json={"conversation_id": chat_id, "query": "tell me about the 2036 gilt"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert posted.status_code == 201, posted.text
        message_id = posted.json()["message_id"]
        assert posted.json()["evidence_bundle_id"] is not None

        got = await client.get(f"/api/v1/research/{message_id}/evidence")
        assert got.status_code == 200
        body = got.json()
        assert body["evidence_bundle_id"] == posted.json()["evidence_bundle_id"]
        assert body["status"] == "READY"
        assert len(body["items"]) >= 1
        assert any(item["metric_id"] == METRIC_GILT_REFERENCE_TERMS for item in body["items"])


async def test_evidence_is_empty_not_404_for_a_reply_with_no_bundle(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as client:
        await _signed_in(client)
        chat_id = await _new_chat(client)

        posted = await client.post(
            "/api/v1/research",
            json={"conversation_id": chat_id, "query": "should I buy this gilt?"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert posted.status_code == 201
        message_id = posted.json()["message_id"]

        got = await client.get(f"/api/v1/research/{message_id}/evidence")
        assert got.status_code == 200
        assert got.json() == {
            "evidence_bundle_id": None, "purpose_type": None, "status": None, "items": [],
        }


async def test_evidence_for_unknown_message_is_not_found(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    async with make_client() as client:
        await _signed_in(client)
        got = await client.get(f"/api/v1/research/{uuid.uuid4()}/evidence")
        assert got.status_code == 404


async def test_evidence_requires_a_session(make_client: ClientFactory) -> None:
    async with make_client() as client:
        got = await client.get(f"/api/v1/research/{uuid.uuid4()}/evidence")
        assert got.status_code == 401


async def test_another_signed_in_user_cannot_read_someone_elses_evidence(
    make_client: ClientFactory, db_session: AsyncSession
) -> None:
    await _seed_pdp_prerequisites(db_session)
    await _seed_gilt_evidence_data(db_session)
    async with make_client() as alice, make_client() as bob:
        await _signed_in(alice)
        chat_id = await _new_chat(alice)
        posted = await alice.post(
            "/api/v1/research",
            json={"conversation_id": chat_id, "query": "tell me about the 2036 gilt"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        message_id = posted.json()["message_id"]

        await _signed_in(bob)
        got = await bob.get(f"/api/v1/research/{message_id}/evidence")
        assert got.status_code == 404
