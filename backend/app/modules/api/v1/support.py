"""Support and Data Quality Anomaly Ticket API."""

from __future__ import annotations

import logging
from typing import Any, Literal, cast

from fastapi import APIRouter, Header, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email_templates.engine import render_talvrin_email_html
from app.modules.api.v1.deps import OptionalIdentityDep, SessionDep
from app.modules.audit.service import record_event
from app.modules.monitoring.delivery import send_transactional_email
from app.modules.support.models import Ticket
from app.modules.support.service import (
    NewTicketEmails,
    create_ticket_with_outbox,
    find_existing_ticket,
    find_ticket_by_key_unbounded,
    mark_dispatch_result,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])

TicketCategory = Literal[
    "data_discrepancy",
    "calculation_error",
    "missing_instrument",
    "platform_glitch",
    "general_inquiry",
]

TicketSeverity = Literal["critical_data_error", "standard", "low"]


class CreateSupportTicketRequest(BaseModel):
    category: TicketCategory
    severity: TicketSeverity = "standard"
    subject: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10, max_length=5000)
    contact_email: EmailStr | None = None
    instrument_symbol: str | None = None
    evidence_bundle_id: str | None = None
    chat_id: str | None = None
    reported_figure: str | None = None
    expected_figure: str | None = None


class SupportTicketResponse(BaseModel):
    ticket_id: str
    status: str
    category: TicketCategory
    severity: TicketSeverity
    created_at: str
    reference_code: str
    message: str


async def _dispatch_support_emails(
    db: AsyncSession,
    ref_code: str,
    ticket_id: str,
    req: CreateSupportTicketRequest,
    account_id: str | None,
    principal_id: str | None,
    dispatches: NewTicketEmails,
) -> None:
    """Attempts to actually send the two emails support.ticket_email_dispatch
    already has durable `queued` rows for (written in the same transaction
    as the ticket, before this function is ever called), and updates each
    row to sent/failed - never leaving a send attempt unrecorded the way
    the old bare `logger.error()` did. Runs after the ticket's own
    transaction has already committed, so a Resend outage can delay or fail
    a notification but can never roll back, block, or otherwise affect the
    ticket itself (InvokeRejected-style fallback boundary, same principle
    AI-001 applies to the AI Gateway).
    """
    settings = get_settings()
    if not settings.smtp_host and not settings.resend_api_key:
        logger.info(
            "No email transport configured; leaving email dispatch for ticket %s queued",
            ref_code,
        )
        return

    # 1. Dispatch internal alert to the support desk mailbox
    desk_body = (
        f"A new institutional ticket has been submitted to the Talvrin platform:\n\n"
        f"• Reference: {ref_code}\n"
        f"• Ticket ID: {ticket_id}\n"
        f"• Category: {req.category}\n"
        f"• Severity: {req.severity.upper()}\n"
        f"• Subject: {req.subject}\n"
        f"• Contact Email: {req.contact_email or 'Not provided'}\n"
        f"• Account ID: {account_id or 'Anonymous (not signed in)'}\n"
        f"• Principal ID: {principal_id or 'Anonymous (not signed in)'}\n"
    )
    if req.instrument_symbol:
        desk_body += f"• Instrument / Symbol: {req.instrument_symbol}\n"
    if req.reported_figure:
        desk_body += f"• Observed Figure: {req.reported_figure}\n"
    if req.expected_figure:
        desk_body += f"• Expected Benchmark Figure: {req.expected_figure}\n"
    if req.evidence_bundle_id:
        desk_body += f"• Evidence Bundle ID: {req.evidence_bundle_id}\n"
    if req.chat_id:
        desk_body += f"• Chat Session ID: {req.chat_id}\n"

    desk_body += f"\nDescription / Memorandum:\n{req.description}\n"

    cat_name = req.category.replace("_", " ").title()
    desk_html = render_talvrin_email_html(
        subject=f"[{ref_code}] New {cat_name} ({req.severity.upper()}): {req.subject}",
        preheader=f"New institutional support ticket {ref_code} received.",
        body_text=desk_body,
        cta_label="View Audit Ledger",
        action_url=f"https://app.talvrin.com/audit?subject_id={ticket_id}",
        badge_label="Support Desk Dispatch",
        notice_reference=ref_code,
    )

    try:
        desk_sent = send_transactional_email(
            to_email=settings.support_inbox_email,
            subject=f"[{ref_code}] New {cat_name} - {req.subject}",
            html_content=desk_html,
        )
        desk_error = None if desk_sent else "email transport reported failure"
        if desk_sent:
            logger.info(
                "Dispatched ticket %s notification to %s",
                ref_code,
                settings.support_inbox_email,
            )
        else:
            logger.error("Failed to email support desk for ticket %s", ref_code)
    except Exception as exc:
        desk_sent = False
        desk_error = str(exc)
        logger.error("Failed to email support desk for ticket %s: %s", ref_code, exc)

    await mark_dispatch_result(
        db, dispatch_id=dispatches.desk_dispatch_id, sent=desk_sent, error=desk_error
    )

    # 2. Dispatch receipt confirmation to user if contact_email was provided
    if req.contact_email:
        user_body = (
            f"Dear Investor,\n\n"
            f'We have received your ticket regarding "{req.subject}". '
            f"Your submission has been recorded on the immutable platform "
            f"audit ledger under reference {ref_code}.\n\n"
            f"Ticket Details:\n"
            f"• Reference Code: {ref_code}\n"
            f"• Category: {req.category.replace('_', ' ').title()}\n"
            f"• Priority: {req.severity.title()}\n"
            f"• Status: Active Review\n\n"
            f"Our quantitative engineering and support team reviews all submissions "
            f"according to your institutional SLA.\n"
            f"You may reply directly to this notification if you wish to provide "
            f"additional bitemporal manifests or filing attachments."
        )

        user_html = render_talvrin_email_html(
            subject=f"Receipt Confirmation: [{ref_code}] {req.subject}",
            preheader=f"Your ticket {ref_code} is recorded on the Talvrin audit ledger.",
            body_text=user_body,
            cta_label="Return to Workspace",
            action_url="https://app.talvrin.com",
            badge_label="Receipt Confirmation",
            notice_reference=ref_code,
        )

        assert dispatches.user_receipt_dispatch_id is not None  # contact_email implies this
        try:
            user_sent = send_transactional_email(
                to_email=req.contact_email,
                subject=f"Receipt Confirmation: [{ref_code}] {req.subject}",
                html_content=user_html,
            )
            user_error = None if user_sent else "email transport reported failure"
            if user_sent:
                logger.info(
                    "Dispatched ticket %s confirmation to %s", ref_code, req.contact_email
                )
            else:
                logger.error("Failed to email user confirmation for ticket %s", ref_code)
        except Exception as exc:
            user_sent = False
            user_error = str(exc)
            logger.error("Failed to email user confirmation for ticket %s: %s", ref_code, exc)

        await mark_dispatch_result(
            db,
            dispatch_id=dispatches.user_receipt_dispatch_id,
            sent=user_sent,
            error=user_error,
        )

    await db.commit()


def _response_from_existing(ticket: Ticket) -> SupportTicketResponse:
    """Builds the response for a duplicate submission - same ticket_id and
    reference_code as the original, so a caller that double-POSTs (slow
    network retry, impatient double-click) can't tell the difference from
    the inside, and never gets a second ticket/second set of emails for it.
    """
    return SupportTicketResponse(
        ticket_id=str(ticket.id),
        status="received",
        category=cast(TicketCategory, ticket.category),
        severity=cast(TicketSeverity, ticket.severity),
        created_at=ticket.created_at.isoformat(),
        reference_code=ticket.reference_code,
        message=(
            f"Support ticket {ticket.reference_code} already received "
            "(duplicate submission - the same Idempotency-Key was reused)."
        ),
    )


@router.post(
    "/tickets",
    response_model=SupportTicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_support_ticket(
    req: CreateSupportTicketRequest,
    db: SessionDep,
    identity: OptionalIdentityDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> SupportTicketResponse:
    """Submit an in-app support request or report a market data discrepancy.

    /contact is a public page (main.tsx has no RequireAuth wrapper on it), so
    a visitor who isn't signed in must be able to reach this too - it
    previously required IdentityDep and 401'd for anyone logged out, which
    the frontend's error handling then silently turned into a mailto: popup
    instead of a real ticket (the actual cause of the reported "Submit
    Ticket to Desk opens Outlook" bug, not a mailto-only implementation).
    An anonymous ticket is recorded honestly as having no account/principal
    rather than attributing it to whichever session happened to be nearby.

    Idempotency-Key is an optional header (standard convention, not a new
    Talvrin-specific one) - today's frontend sends nothing, which must keep
    behaving exactly as before (every call creates a new ticket). When a
    caller does send one, a repeat within 24h of the same key (scoped to
    this account, or to the shared anonymous bucket when signed out - see
    support/models.py's Ticket docstring) returns the ORIGINAL ticket's
    response rather than creating a second ticket/second set of emails.
    """
    account_id = identity.account_id if identity else None
    principal_id = identity.principal_id if identity else None

    if idempotency_key:
        existing = await find_existing_ticket(
            db, account_id=account_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            logger.info(
                "Duplicate support ticket submission suppressed for key %s -> %s",
                idempotency_key,
                existing.reference_code,
            )
            return _response_from_existing(existing)

    ticket, dispatches = await create_ticket_with_outbox(
        db,
        account_id=account_id,
        principal_id=principal_id,
        idempotency_key=idempotency_key,
        reference_code="",  # placeholder, fixed up below once the id exists
        category=req.category,
        severity=req.severity,
        subject=req.subject,
        description=req.description,
        contact_email=req.contact_email,
        instrument_symbol=req.instrument_symbol,
        evidence_bundle_id=req.evidence_bundle_id,
        chat_id=req.chat_id,
        reported_figure=req.reported_figure,
        expected_figure=req.expected_figure,
        support_inbox_email=get_settings().support_inbox_email,
    )
    ticket_id = str(ticket.id)
    # uuid7's leading 48 bits are a millisecond timestamp (DATA-001) - the
    # first 8 hex chars barely change for ~65s at a time (they're bits
    # 0-31 of that timestamp), so two tickets filed within the same
    # ~65-second window used to mint the identical reference_code and
    # collide on uq_ticket_reference_code (confirmed live by the test
    # suite's own back-to-back POSTs). The last 8 hex chars fall entirely
    # within uuid7's random tail (rand_b), so they're actually unique.
    ref_code = f"TAL-{ticket_id.replace('-', '')[-8:].upper()}"
    ticket.reference_code = ref_code

    payload: dict[str, Any] = {
        "ticket_id": ticket_id,
        "reference_code": ref_code,
        "account_id": str(account_id) if account_id else None,
        "principal_id": str(principal_id) if principal_id else None,
        "category": req.category,
        "severity": req.severity,
        "subject": req.subject,
        "description": req.description,
        "contact_email": req.contact_email,
        "instrument_symbol": req.instrument_symbol,
        "evidence_bundle_id": req.evidence_bundle_id,
        "chat_id": req.chat_id,
        "reported_figure": req.reported_figure,
        "expected_figure": req.expected_figure,
    }

    # Record into audit trail for forensic traceability
    await record_event(
        db,
        event_type="support.ticket_created",
        actor_principal_id=principal_id,
        subject_type="support_ticket",
        subject_id=ticket_id,
        payload=payload,
    )
    # get_session's own contract is "callers commit explicitly" - this was
    # missing entirely (confirmed live: a submitted ticket returned 201 with
    # a reference code, but a fresh connection to the real database showed
    # no row at all). Every ticket ever submitted through this endpoint was
    # silently discarded on session teardown - a false "received" response,
    # not a working one. Must commit before dispatching email, so a ticket
    # is never emailed as proof of receipt unless it is actually durable.
    #
    # A concurrent duplicate (two requests racing the exact same
    # Idempotency-Key, both passing the find_existing_ticket check above
    # because neither had committed yet) surfaces here as an IntegrityError
    # against support.ix_ticket_idempotency - the loser rolls back and
    # returns whatever the winner actually committed, rather than a 500 or
    # a silently-accepted second ticket.
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Unbounded, not find_existing_ticket: the index this just violated
        # has no time dimension, so the conflicting row might be older than
        # IDEMPOTENCY_WINDOW even though the pre-check above found nothing.
        existing = await find_ticket_by_key_unbounded(
            db, account_id=account_id, idempotency_key=idempotency_key or ""
        )
        if existing is None:  # pragma: no cover - would mean a different constraint fired
            raise
        return _response_from_existing(existing)

    # Attempt to actually send the two emails whose `queued` outbox rows
    # just committed above - on any failure (including a raised exception,
    # not just a non-2xx response) the row is updated to `failed` rather
    # than only logged, and the ticket itself is already durable regardless
    # of how this goes.
    await _dispatch_support_emails(
        db,
        ref_code=ref_code,
        ticket_id=ticket_id,
        req=req,
        account_id=str(account_id) if account_id else None,
        principal_id=str(principal_id) if principal_id else None,
        dispatches=dispatches,
    )

    return SupportTicketResponse(
        ticket_id=ticket_id,
        status="received",
        category=req.category,
        severity=req.severity,
        created_at=ticket.created_at.isoformat(),
        reference_code=ref_code,
        message=f"Support ticket {ref_code} received and dispatched to email.",
    )
