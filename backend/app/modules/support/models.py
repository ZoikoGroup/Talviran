"""support schema (UAT gap G08) - a durable row per ticket, plus a
transactional outbox for the emails each ticket owes.

Before this module existed, "a support ticket" was never a row anywhere -
api/v1/support.py only ever wrote an audit.event_log entry (a forensic
record, not a queryable/dedup-able entity) and minted a fresh uuid.uuid4()
on every call, so a duplicate HTTP POST created two of everything. Ticket
is that first durable row; its id *is* the ticket_id returned to callers.
"""

import datetime as dt
import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

TICKET_EMAIL_QUEUED = "queued"
TICKET_EMAIL_SENT = "sent"
TICKET_EMAIL_FAILED = "failed"

TICKET_EMAIL_KIND_DESK_ALERT = "desk_alert"
TICKET_EMAIL_KIND_USER_RECEIPT = "user_receipt"


class Ticket(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One row per support ticket (data-discrepancy report, platform bug,
    general inquiry, ...). No FKs on account_id/principal_id, matching
    audit.EventLog's own choice: /contact has no RequireAuth wrapper, so an
    anonymous visitor must be able to create one with neither set, and a
    ticket must survive independently of the principal/account that filed
    it (including across a later account deletion).

    idempotency_key is optional - only present when the caller sent an
    Idempotency-Key header. The real dedup guarantee lives in the partial,
    coalescing unique index this table's migration creates directly in
    Postgres (ix_ticket_idempotency), not in any uniqueness declared here -
    SQLAlchemy's Core/ORM layer has no portable way to express "COALESCE
    account_id to a sentinel inside a unique index", so that index is
    raw DDL in the migration and deliberately not mirrored as a
    UniqueConstraint/Index on this model (a model-level one would be
    wrong - it would compare account_id bare, where NULL <> NULL, which is
    exactly the bug this index exists to avoid).
    """

    __tablename__ = "ticket"
    __table_args__ = {"schema": "support"}

    account_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    principal_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    reference_code: Mapped[str] = mapped_column(String(32), unique=True)
    category: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(5000))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    instrument_symbol: Mapped[str | None] = mapped_column(String(64))
    evidence_bundle_id: Mapped[str | None] = mapped_column(String(64))
    chat_id: Mapped[str | None] = mapped_column(String(64))
    reported_figure: Mapped[str | None] = mapped_column(String(200))
    expected_figure: Mapped[str | None] = mapped_column(String(200))


class TicketEmailDispatch(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Transactional outbox row for one email a ticket owes (MON-001's
    AlertDeliveryAttempt and market.OutboxEvent are the same pattern
    applied elsewhere in this codebase - this isn't a new idiom). Written
    as `queued` in the SAME transaction/commit as the Ticket row it
    belongs to, so a ticket is never "receiptable" without a durable
    notification record even before anything has actually tried to send.
    The request handler updates status to sent/failed in a second commit
    after attempting delivery via Resend.

    No background retry worker reads `failed` rows back yet - that's
    separate SRE infra work the G08 gap explicitly scopes out - but
    attempt_count/last_error/status make a `failed` row identifiable and
    retryable by one once it exists, rather than lost like the bare
    `logger.error()` call this replaces.
    """

    __tablename__ = "ticket_email_dispatch"
    __table_args__ = {"schema": "support"}

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("support.ticket.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    recipient_email: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(16), default=TICKET_EMAIL_QUEUED, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[dt.datetime] = mapped_column(
        default=lambda: dt.datetime.now(dt.UTC), onupdate=lambda: dt.datetime.now(dt.UTC)
    )
