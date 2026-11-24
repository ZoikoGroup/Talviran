"""Alert delivery (MON-001 §14) - transports: IN_APP and EMAIL via Resend."""

import json
import logging
import smtplib
import ssl
import urllib.request
import uuid
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.monitoring.models import (
    ALERT_TYPE_CROSSING,
    DELIVERY_ATTEMPT_DELIVERED,
    DELIVERY_ATTEMPT_FAILED,
    STATUS_ALERT_DELIVERED,
    STATUS_ALERT_SUPPRESSED,
    TRANSPORT_EMAIL,
    TRANSPORT_IN_APP,
    Alert,
    AlertDeliveryAttempt,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliverySkipped:
    reason: str


@dataclass(frozen=True)
class Delivered:
    alert_id: uuid.UUID


async def _next_attempt_number(
    session: AsyncSession, *, alert_id: uuid.UUID, transport: str
) -> int:
    """Computes the sequential attempt number for (alert_id, transport)."""
    current_max = (
        await session.execute(
            select(func.max(AlertDeliveryAttempt.attempt_number)).where(
                AlertDeliveryAttempt.alert_id == alert_id,
                AlertDeliveryAttempt.transport == transport,
            )
        )
    ).scalar_one_or_none()
    return (current_max or 0) + 1


def _send_resend_email(
    to_email: str,
    subject: str,
    html_content: str,
    api_key: str,
    from_email: str,
    attachments: list[dict[str, str]] | None = None,
) -> bool:
    """Dispatches transactional email via Resend API."""
    try:
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Talvrin-Alert-Engine/1.0",
        }
        payload: dict[str, object] = {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
        }
        if attachments:
            payload["attachments"] = attachments
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 201)
    except Exception as exc:
        logger.warning("Failed to dispatch alert via Resend: %s", exc)
        return False


def _send_smtp_email(
    to_email: str,
    subject: str,
    html_content: str,
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    from_email: str,
) -> bool:
    """Dispatches transactional email via a direct SMTP connection to a real
    hosted mailbox (e.g. GoDaddy's smtpout.secureserver.net). Port 465 is
    implicit TLS (SMTP_SSL); anything else is plain SMTP upgraded with
    STARTTLS - the two connection modes a hosted mailbox actually offers.
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        msg.attach(MIMEText(html_content, "html"))

        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=10, context=context) as server:
                server.login(user, password)
                server.sendmail(from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls(context=context)
                server.login(user, password)
                server.sendmail(from_email, [to_email], msg.as_string())
        return True
    except Exception as exc:
        logger.warning("Failed to dispatch email via SMTP to %s: %s", to_email, exc)
        return False


def send_transactional_email(to_email: str, subject: str, html_content: str) -> bool:
    """Single entry point for transactional email (ticket receipts, desk
    notifications, etc.): a configured SMTP mailbox is used in preference to
    Resend, so callers never need to know or care which transport is
    actually wired up in this environment. Logs and returns False rather
    than raising when neither transport is configured.
    """
    settings = get_settings()

    if settings.smtp_host and settings.smtp_user and settings.smtp_pass:
        return _send_smtp_email(
            to_email,
            subject,
            html_content,
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user.get_secret_value(),
            password=settings.smtp_pass.get_secret_value(),
            from_email=settings.smtp_from or settings.smtp_user.get_secret_value(),
        )

    if settings.resend_api_key:
        return _send_resend_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            api_key=settings.resend_api_key.get_secret_value(),
            from_email=settings.support_from_email or settings.alerts_from_email,
        )

    logger.info("No email transport configured; skipping send to %s", to_email)
    return False


# send_market_alert_email used to live here: a caller-controlled email
# dispatcher with no verification against any real Alert/MonitoringRule row
# (removed alongside its only caller, api/v1/alerts.py's POST /trigger
# endpoint - see that module's docstring, 2026-11-10 UAT gap analysis G11
# remediation). deliver_alert below, driven entirely by a real persisted
# Alert row, remains the only path that ever sends an alert email.


async def deliver_alert(
    session: AsyncSession, *, alert_id: uuid.UUID, recipient_email: str | None = None
) -> Delivered | DeliverySkipped:
    """Delivers alert to in-app inbox and automatically dispatches via Resend email
    if recipient_email and resend_api_key are configured.
    """
    alert = await session.get(Alert, alert_id)
    if alert is None:
        return DeliverySkipped(reason=f"no alert {alert_id}")

    if alert.status == STATUS_ALERT_DELIVERED:
        return Delivered(alert_id=alert.id)
    if alert.status == STATUS_ALERT_SUPPRESSED:
        return DeliverySkipped(reason=f"alert {alert_id} is suppressed, not deliverable")

    # 1. In-App delivery attempt: only add if not already delivered
    existing_in_app = (
        await session.execute(
            select(AlertDeliveryAttempt).where(
                AlertDeliveryAttempt.alert_id == alert.id,
                AlertDeliveryAttempt.transport == TRANSPORT_IN_APP,
                AlertDeliveryAttempt.status == DELIVERY_ATTEMPT_DELIVERED,
            )
        )
    ).scalar_one_or_none()

    if existing_in_app is None:
        in_app_attempt = await _next_attempt_number(
            session, alert_id=alert.id, transport=TRANSPORT_IN_APP
        )
        session.add(
            AlertDeliveryAttempt(
                account_id=alert.account_id,
                alert_id=alert.id,
                transport=TRANSPORT_IN_APP,
                attempt_number=in_app_attempt,
                status=DELIVERY_ATTEMPT_DELIVERED,
            )
        )

    # 2. Email delivery: only dispatch for actual threshold CROSSING alerts
    # (INITIAL_STATE represents the benchmark baseline when a rule was first
    # evaluated, not a crossing worth emailing about), and only when the
    # firing rule version asked for it. Goes through send_transactional_email
    # - the same SMTP-preferred, Resend-fallback entry point support.py's
    # ticket receipts use - never a bespoke second mail path with its own
    # transport-selection logic (a bare settings.resend_api_key gate here
    # would silently skip EMAIL delivery in an SMTP-only environment).
    if recipient_email and alert.alert_type == ALERT_TYPE_CROSSING:
        subject = f"[Talvrin Alert] {alert.metric_id} threshold crossed"
        metric_str = alert.metric_id
        thresh_str = str(alert.threshold_value)
        obs_str = str(alert.observed_value)
        time_str = alert.knowledge_time.strftime("%Y-%m-%d %H:%M:%S") + " UTC"

        from app.core.email_templates.engine import render_talvrin_email_html

        body_text = (
            f"An automated surveillance trigger on your Talvrin account has executed.\n\n"
            f"Asset / Metric: {metric_str}\n"
            f"Target Threshold: {thresh_str}\n"
            f"Observed Value: {obs_str}\n"
            f"Trigger Reference Time: {time_str}\n\n"
            f"This delivery is an objective record generated against approved accepted facts and canonical pricing methodology."
        )

        html = render_talvrin_email_html(
            subject=subject,
            preheader=f"Automated surveillance trigger: {metric_str} observed {obs_str} against target {thresh_str}.",
            body_text=body_text,
            cta_label="Inspect Market Alert",
            action_url="https://app.talvrin.com",
            badge_label="Objective Alert",
            notice_reference="TAL-EML-MO-MONITOR_MATCH",
        )

        success = send_transactional_email(
            to_email=recipient_email, subject=subject, html_content=html
        )

        email_attempt = await _next_attempt_number(
            session, alert_id=alert.id, transport=TRANSPORT_EMAIL
        )
        session.add(
            AlertDeliveryAttempt(
                account_id=alert.account_id,
                alert_id=alert.id,
                transport=TRANSPORT_EMAIL,
                attempt_number=email_attempt,
                status=DELIVERY_ATTEMPT_DELIVERED if success else DELIVERY_ATTEMPT_FAILED,
            )
        )

    alert.status = STATUS_ALERT_DELIVERED
    await session.flush()
    return Delivered(alert_id=alert.id)
