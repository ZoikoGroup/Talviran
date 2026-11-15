"""POST /api/v1/support/tickets must accept an anonymous submitter.

/contact (frontend/src/main.tsx) has no RequireAuth wrapper - any visitor can
reach it without signing in. The endpoint used to require IdentityDep and
401 for exactly that visitor, and the frontend's catch-block silently turned
that failure into a mailto: popup instead of a real ticket - the actual
cause of bug T7 ("Submit Ticket to Desk opens Outlook"), not a mailto-only
implementation. record_event's actor_principal_id is nullable precisely so
an anonymous ticket can be recorded honestly rather than attributed to
whichever session happened to be nearby.
"""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import get_session
from app.main import create_app
from app.modules.audit.models import EventLog


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


_PAYLOAD = {
    "category": "general_inquiry",
    "subject": "Contact form test",
    "description": "A question about coverage, asked while signed out.",
}


async def test_an_anonymous_visitor_can_submit_a_ticket(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    r = await client.post("/api/v1/support/tickets", json=_PAYLOAD)
    assert r.status_code == 201
    body = r.json()
    assert body["reference_code"].startswith("TAL-")
    assert body["status"] == "received"

    # Recorded honestly as having no account/principal, not attributed to a
    # session that was never actually presented.
    row = (
        await db_session.execute(
            select(EventLog).where(EventLog.subject_id == body["ticket_id"])
        )
    ).scalar_one()
    assert row.actor_principal_id is None
    assert row.payload["account_id"] is None
    assert row.payload["principal_id"] is None


async def test_the_response_never_claims_outlook_is_involved(client: httpx.AsyncClient) -> None:
    """A real backend response, not a client-side mailto: fallback."""
    r = await client.post("/api/v1/support/tickets", json=_PAYLOAD)
    assert r.status_code == 201
    assert "ticket_id" in r.json()


async def test_the_ticket_is_actually_committed_not_just_returned(
    client: httpx.AsyncClient,
) -> None:
    """Confirmed live and by direct inspection: this endpoint never called
    db.commit() at all. get_session's own contract is "callers commit
    explicitly" (app/core/db.py), so every ticket ever submitted was
    silently rolled back on session teardown - a 201 with a reference code
    for a row that was never actually saved. The test above using the same
    overridden `db_session` object could never have caught this: a session
    sees its own uncommitted writes regardless of whether commit() was
    called, so it would pass either way. This test opens a genuinely
    separate connection - the only way to prove the row is durable rather
    than just visible to the request that wrote it.
    """
    r = await client.post("/api/v1/support/tickets", json=_PAYLOAD)
    assert r.status_code == 201
    ticket_id = r.json()["ticket_id"]

    engine = create_async_engine(get_settings().test_database_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as independent_session:
            row = (
                await independent_session.execute(
                    select(EventLog).where(EventLog.subject_id == ticket_id)
                )
            ).scalar_one_or_none()
            assert row is not None, (
                "ticket row is invisible to a separate connection - "
                "db.commit() regressed"
            )
    finally:
        await engine.dispose()
