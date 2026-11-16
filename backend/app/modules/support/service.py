"""Service layer for support.ticket / support.ticket_email_dispatch - the
only code api/v1/support.py should reach into these tables through (same
no-cross-module-direct-write discipline every other module follows).
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uuid7 import new_uuid7
from app.modules.support.models import (
    TICKET_EMAIL_FAILED,
    TICKET_EMAIL_KIND_DESK_ALERT,
    TICKET_EMAIL_KIND_USER_RECEIPT,
    TICKET_EMAIL_QUEUED,
    TICKET_EMAIL_SENT,
    Ticket,
    TicketEmailDispatch,
)

# How far back a repeated Idempotency-Key is still honoured. Past this, a
# resend with the same key is treated as a genuinely new ticket rather than
# a duplicate of one that's ancient history - matches the task's own "a
# reasonable window (e.g. 24 hours)".
IDEMPOTENCY_WINDOW = dt.timedelta(hours=24)


@dataclass(frozen=True)
class NewTicketEmails:
    """What the router needs to actually attempt sending, once outbox rows
    already exist durably in the same transaction as the ticket.
    """

    desk_dispatch_id: uuid.UUID
    user_receipt_dispatch_id: uuid.UUID | None


async def find_existing_ticket(
    session: AsyncSession, *, account_id: uuid.UUID | None, idempotency_key: str
) -> Ticket | None:
    """Looks up a ticket already created for this (account-or-anonymous,
    idempotency_key) pair within IDEMPOTENCY_WINDOW, matching the partial
    unique index support.ix_ticket_idempotency enforces in Postgres (this
    query compares account_id with IS NOT DISTINCT FROM precisely so NULL
    matches NULL here too, the same coalescing intent that index expresses
    with COALESCE(...) - a bare `==` would miss every anonymous ticket).

    This is the fast-path, pre-insert check - called BEFORE attempting to
    create a ticket. Use find_ticket_by_key_unbounded (no window) to
    resolve an actual UniqueViolation from that index; the index itself
    has no time dimension (Postgres partial indexes require an immutable
    predicate, so "created within the last 24h" can't be expressed in the
    index itself), so a key reused just past the window would otherwise
    raise on insert here and then find nothing in a still-windowed lookup
    - a 500 for a case the index is actually handling correctly.
    """
    cutoff = dt.datetime.now(dt.UTC) - IDEMPOTENCY_WINDOW
    stmt = select(Ticket).where(
        Ticket.account_id.is_not_distinct_from(account_id),
        Ticket.idempotency_key == idempotency_key,
        Ticket.created_at >= cutoff,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def find_ticket_by_key_unbounded(
    session: AsyncSession, *, account_id: uuid.UUID | None, idempotency_key: str
) -> Ticket | None:
    """Same lookup as find_existing_ticket but with no IDEMPOTENCY_WINDOW
    cutoff - the authoritative resolution for an actual UniqueViolation
    against support.ix_ticket_idempotency, which enforces uniqueness
    forever, not just within the window. Only meant to be called after a
    concurrent/post-window duplicate insert has already been rejected by
    Postgres: at that point some row with this key definitely exists,
    regardless of its age, and the right response is always "return it",
    never a 500.
    """
    stmt = select(Ticket).where(
        Ticket.account_id.is_not_distinct_from(account_id),
        Ticket.idempotency_key == idempotency_key,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_ticket_with_outbox(
    session: AsyncSession,
    *,
    account_id: uuid.UUID | None,
    principal_id: uuid.UUID | None,
    idempotency_key: str | None,
    reference_code: str,
    category: str,
    severity: str,
    subject: str,
    description: str,
    contact_email: str | None,
    instrument_symbol: str | None,
    evidence_bundle_id: str | None,
    chat_id: str | None,
    reported_figure: str | None,
    expected_figure: str | None,
    support_inbox_email: str,
) -> tuple[Ticket, NewTicketEmails]:
    """Adds a Ticket row plus its queued TicketEmailDispatch row(s) to
    `session` - does NOT commit (get_session's contract is "callers commit
    explicitly"; the caller commits this together with its own audit.
    record_event call, so a ticket is never "receiptable" without both its
    audit trail entry and its outbox rows already durable).

    On a concurrent duplicate (two requests racing the exact same
    idempotency key, both passing the pre-check in find_existing_ticket
    because neither had committed yet), the unique index itself is the
    real guard: this function lets the caller's commit raise
    IntegrityError, which the router catches, rolls back, and re-resolves
    by calling find_existing_ticket again - this function doesn't catch
    that itself because it never commits.
    """
    ticket = Ticket(
        id=new_uuid7(),
        account_id=account_id,
        principal_id=principal_id,
        idempotency_key=idempotency_key,
        reference_code=reference_code,
        category=category,
        severity=severity,
        subject=subject,
        description=description,
        contact_email=contact_email,
        instrument_symbol=instrument_symbol,
        evidence_bundle_id=evidence_bundle_id,
        chat_id=chat_id,
        reported_figure=reported_figure,
        expected_figure=expected_figure,
    )
    session.add(ticket)

    # id= is explicit here, not left to UUIDPrimaryKeyMixin's column default,
    # for the same reason Ticket's own id is explicit above: a Python-side
    # mapped_column(default=...) is only evaluated when the flush actually
    # builds the INSERT, so `.id` would still read None if accessed (as it
    # is a few lines down, for NewTicketEmails) before any flush happens.
    desk_dispatch = TicketEmailDispatch(
        id=new_uuid7(),
        ticket_id=ticket.id,
        kind=TICKET_EMAIL_KIND_DESK_ALERT,
        recipient_email=support_inbox_email,
        status=TICKET_EMAIL_QUEUED,
    )
    session.add(desk_dispatch)

    user_dispatch: TicketEmailDispatch | None = None
    if contact_email:
        user_dispatch = TicketEmailDispatch(
            id=new_uuid7(),
            ticket_id=ticket.id,
            kind=TICKET_EMAIL_KIND_USER_RECEIPT,
            recipient_email=contact_email,
            status=TICKET_EMAIL_QUEUED,
        )
        session.add(user_dispatch)

    return ticket, NewTicketEmails(
        desk_dispatch_id=desk_dispatch.id,
        user_receipt_dispatch_id=user_dispatch.id if user_dispatch else None,
    )


async def mark_dispatch_result(
    session: AsyncSession, *, dispatch_id: uuid.UUID, sent: bool, error: str | None
) -> None:
    """Updates one outbox row after an actual send attempt - called after
    the ticket's own transaction already committed, in a second commit, so
    an email transport hiccup can never roll back or block the ticket
    itself. A `failed` row is left exactly as-is otherwise: identifiable
    (status/last_error) and retryable (nothing here marks it as dead) by a
    future worker that isn't built as part of this change.
    """
    dispatch = await session.get(TicketEmailDispatch, dispatch_id)
    if dispatch is None:  # pragma: no cover - defensive, shouldn't happen
        return
    dispatch.attempt_count += 1
    dispatch.status = TICKET_EMAIL_SENT if sent else TICKET_EMAIL_FAILED
    dispatch.last_error = None if sent else (error or "unknown error")[:500]


__all__ = [
    "IDEMPOTENCY_WINDOW",
    "NewTicketEmails",
    "create_ticket_with_outbox",
    "find_existing_ticket",
    "find_ticket_by_key_unbounded",
    "mark_dispatch_result",
]
