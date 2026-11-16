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

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import get_session
from app.main import create_app
from app.modules.audit.models import EventLog
from app.modules.support.models import TICKET_EMAIL_FAILED, Ticket, TicketEmailDispatch


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


class _NoTransportSettings:
    """Real-looking settings with no email transport configured.

    Without this, these tests pick up whatever real SMTP/Resend credentials
    happen to be in the developer's own .env (get_settings() reads it same
    as the dev server does) and send genuine email through them on every
    test run - confirmed: before this fixture existed, a single local test
    run sent several real emails through the live SMTP mailbox. Tests that
    specifically want to exercise the dispatch path override
    app.modules.api.v1.support.get_settings/send_transactional_email
    themselves, which simply wins by running later in the same test.
    """

    resend_api_key: str | None = None
    smtp_host = None
    smtp_port = 465
    smtp_user = None
    smtp_pass = None
    smtp_from = None
    support_from_email = "support@app.talvrin.com"
    alerts_from_email = "alerts@app.talvrin.com"
    support_inbox_email = "talvrin@zoikogroup.com"


@pytest.fixture(autouse=True)
def _no_real_email_transport_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.api.v1.support.get_settings", lambda: _NoTransportSettings()
    )


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


async def test_a_double_submission_with_the_same_idempotency_key_is_one_ticket(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """G08: a slow-network retry or an impatient double-click POSTs the
    exact same request twice with the same client-generated Idempotency-Key.
    Before this change, every call minted a fresh uuid.uuid4() unconditionally
    - two tickets, two audit rows, two sets of emails for one real request.
    """
    key = f"test-{uuid.uuid4()}"
    r1 = await client.post(
        "/api/v1/support/tickets", json=_PAYLOAD, headers={"Idempotency-Key": key}
    )
    r2 = await client.post(
        "/api/v1/support/tickets", json=_PAYLOAD, headers={"Idempotency-Key": key}
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    body1, body2 = r1.json(), r2.json()
    assert body1["ticket_id"] == body2["ticket_id"]
    assert body1["reference_code"] == body2["reference_code"]

    # Exactly one row, not two, actually landed in support.ticket.
    rows = (
        await db_session.execute(
            select(Ticket).where(Ticket.idempotency_key == key)
        )
    ).scalars().all()
    assert len(rows) == 1


async def test_distinct_or_missing_idempotency_keys_still_create_two_tickets(
    client: httpx.AsyncClient,
) -> None:
    """Confirms the new idempotency path hasn't broken ordinary distinct
    submissions - the overwhelming majority of callers today, since the
    frontend doesn't send this header at all yet.
    """
    r1 = await client.post("/api/v1/support/tickets", json=_PAYLOAD)
    r2 = await client.post("/api/v1/support/tickets", json=_PAYLOAD)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["ticket_id"] != r2.json()["ticket_id"]

    key_a, key_b = f"test-{uuid.uuid4()}", f"test-{uuid.uuid4()}"
    r3 = await client.post(
        "/api/v1/support/tickets", json=_PAYLOAD, headers={"Idempotency-Key": key_a}
    )
    r4 = await client.post(
        "/api/v1/support/tickets", json=_PAYLOAD, headers={"Idempotency-Key": key_b}
    )
    assert r3.status_code == 201 and r4.status_code == 201
    assert r3.json()["ticket_id"] != r4.json()["ticket_id"]


async def test_a_failed_email_send_still_leaves_a_durable_failed_ticket(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates a Resend/DB-adjacent outage at send time: _send_resend_email
    itself raises (standing in for a network failure, not just a non-2xx
    response the real function already turns into `False`). The ticket must
    still be durably created and returned 201 - never lost, never blocking
    the response - with its outbox row left `failed` and therefore
    identifiable/retryable, not silently dropped the way a bare
    `logger.error()` used to leave it.
    """

    class _FakeSettingsWithTransport(_NoTransportSettings):
        # Must be truthy so _dispatch_support_emails's "no transport
        # configured" early-return doesn't skip the send attempt below
        # before send_transactional_email (mocked to fail) is ever reached.
        resend_api_key = "test-key-not-real"

    monkeypatch.setattr(
        "app.modules.api.v1.support.get_settings", lambda: _FakeSettingsWithTransport()
    )

    def _boom(**kwargs: object) -> bool:
        raise RuntimeError("simulated Resend outage")

    monkeypatch.setattr("app.modules.api.v1.support.send_transactional_email", _boom)

    payload = {**_PAYLOAD, "contact_email": "investor@example.com"}
    r = await client.post("/api/v1/support/tickets", json=payload)
    assert r.status_code == 201
    ticket_id = r.json()["ticket_id"]

    ticket = (
        await db_session.execute(select(Ticket).where(Ticket.id == uuid.UUID(ticket_id)))
    ).scalar_one()
    assert ticket.reference_code == r.json()["reference_code"]

    dispatches = (
        await db_session.execute(
            select(TicketEmailDispatch).where(
                TicketEmailDispatch.ticket_id == uuid.UUID(ticket_id)
            )
        )
    ).scalars().all()
    assert len(dispatches) == 2, "desk alert + user receipt, contact_email was provided"
    assert all(d.status == TICKET_EMAIL_FAILED for d in dispatches)
    assert all(d.last_error and "simulated Resend outage" in d.last_error for d in dispatches)
    assert all(d.attempt_count == 1 for d in dispatches)
