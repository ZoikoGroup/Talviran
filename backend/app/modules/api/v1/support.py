"""Support and Data Quality Anomaly Ticket API."""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, EmailStr, Field

from app.core.config import get_settings
from app.core.email_templates.engine import render_talvrin_email_html
from app.modules.api.v1.deps import IdentityDep, SessionDep
from app.modules.audit.service import record_event
from app.modules.monitoring.delivery import _send_resend_email

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


def _dispatch_support_emails(
    ref_code: str,
    ticket_id: str,
    req: CreateSupportTicketRequest,
    account_id: str,
    principal_id: str,
) -> None:
    """Dispatches notification emails to both the institutional support desk and the sender."""
    settings = get_settings()
    if not settings.resend_api_key:
        logger.info(
            "Resend API key not configured; skipping email dispatch for ticket %s",
            ref_code,
        )
        return

    from_email = settings.support_from_email or settings.alerts_from_email

    # 1. Dispatch internal alert to institutional desk (talvrin@zoikogroup.com)
    desk_body = (
        f"A new institutional ticket has been submitted to the Talvrin platform:\n\n"
        f"• Reference: {ref_code}\n"
        f"• Ticket ID: {ticket_id}\n"
        f"• Category: {req.category}\n"
        f"• Severity: {req.severity.upper()}\n"
        f"• Subject: {req.subject}\n"
        f"• Contact Email: {req.contact_email or 'Not provided'}\n"
        f"• Account ID: {account_id}\n"
        f"• Principal ID: {principal_id}\n"
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
        _send_resend_email(
            to_email=settings.support_inbox_email,
            subject=f"[{ref_code}] New {cat_name} - {req.subject}",
            html_content=desk_html,
            api_key=settings.resend_api_key,
            from_email=from_email,
        )
        logger.info(
            "Dispatched ticket %s notification to %s",
            ref_code,
            settings.support_inbox_email,
        )
    except Exception as exc:
        logger.error("Failed to email support desk for ticket %s: %s", ref_code, exc)

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

        try:
            _send_resend_email(
                to_email=req.contact_email,
                subject=f"Receipt Confirmation: [{ref_code}] {req.subject}",
                html_content=user_html,
                api_key=settings.resend_api_key,
                from_email=from_email,
            )
            logger.info("Dispatched ticket %s confirmation to %s", ref_code, req.contact_email)
        except Exception as exc:
            logger.error("Failed to email user confirmation for ticket %s: %s", ref_code, exc)


@router.post(
    "/tickets",
    response_model=SupportTicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_support_ticket(
    req: CreateSupportTicketRequest,
    db: SessionDep,
    identity: IdentityDep,
) -> SupportTicketResponse:
    """Submit an in-app support request or report a market data discrepancy."""
    ticket_id = str(uuid.uuid4())
    ref_code = f"TAL-{ticket_id[:8].upper()}"

    payload: dict[str, Any] = {
        "ticket_id": ticket_id,
        "reference_code": ref_code,
        "account_id": str(identity.account_id),
        "principal_id": str(identity.principal_id),
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
        actor_principal_id=identity.principal_id,
        subject_type="support_ticket",
        subject_id=ticket_id,
        payload=payload,
    )

    # Dispatch email alerts asynchronously (to support desk + user confirmation)
    _dispatch_support_emails(
        ref_code=ref_code,
        ticket_id=ticket_id,
        req=req,
        account_id=str(identity.account_id),
        principal_id=str(identity.principal_id),
    )

    return SupportTicketResponse(
        ticket_id=ticket_id,
        status="received",
        category=req.category,
        severity=req.severity,
        created_at=dt.datetime.now(dt.UTC).isoformat(),
        reference_code=ref_code,
        message=f"Support ticket {ref_code} received and dispatched to email.",
    )
