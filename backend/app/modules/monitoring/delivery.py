"""Alert delivery (MON-001 §14) - transports: IN_APP and EMAIL via Resend."""

import datetime as dt
import json
import logging
import urllib.request
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.monitoring.models import (
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


def _send_resend_email(
    to_email: str,
    subject: str,
    html_content: str,
    api_key: str,
    from_email: str,
) -> bool:
    """Dispatches transactional email via Resend API."""
    try:
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Talvrin-Alert-Engine/1.0",
        }
        payload = {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 201)
    except Exception as exc:
        logger.warning("Failed to dispatch alert via Resend: %s", exc)
        return False


def send_market_alert_email(
    *,
    recipient_email: str,
    asset_symbol: str,
    asset_name: str | None,
    threshold_value: str,
    observed_value: str,
    predicate: str = "CROSSES_ABOVE",
) -> bool:
    """Dispatches a market threshold alert using canonical Talvrin template design and branding."""
    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning("Cannot dispatch alert email: resend_api_key is not configured")
        return False

    direction_str = "rises above" if predicate == "CROSSES_ABOVE" else "falls below"
    display_title = f"{asset_symbol}" + (f" ({asset_name})" if asset_name else "")
    subject = f"Verified threshold event: {display_title}"
    preheader = f"Monitored threshold crossed: {asset_symbol} touched {observed_value} ({direction_str} {threshold_value})."
    time_str = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S") + " UTC"

    body_text = (
        f"A monitored price condition was met using an entitled, validated price observation on your Talvrin account.\n\n"
        f"Asset: {display_title}\n"
        f"Target Threshold: {threshold_value} ({direction_str})\n"
        f"Observed / Touched Price: {observed_value}\n"
        f"Trigger Reference Time: {time_str}\n\n"
        f"This alert has touched its target, is now fulfilled, and has been archived into your Trigger History."
    )

    from app.core.email_templates.engine import render_talvrin_email_html

    html_content = render_talvrin_email_html(
        subject=subject,
        preheader=preheader,
        body_text=body_text,
        cta_label="Inspect Price Evidence",
        action_url="https://app.talvrin.com",
        badge_label="Objective Alert",
        notice_reference="TAL-EML-MO-PRICE_CROSS",
    )

    return _send_resend_email(
        to_email=recipient_email,
        subject=subject,
        html_content=html_content,
        api_key=settings.resend_api_key,
        from_email=settings.alerts_from_email,
    )




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

    # 1. In-App delivery attempt
    session.add(
        AlertDeliveryAttempt(
            account_id=alert.account_id,
            alert_id=alert.id,
            transport=TRANSPORT_IN_APP,
            attempt_number=1,
            status=DELIVERY_ATTEMPT_DELIVERED,
        )
    )

    # 2. Resend Email delivery if configured
    settings = get_settings()
    if settings.resend_api_key and recipient_email:
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

        success = _send_resend_email(
            to_email=recipient_email,
            subject=subject,
            html_content=html,
            api_key=settings.resend_api_key,
            from_email=settings.alerts_from_email,
        )

        session.add(
            AlertDeliveryAttempt(
                account_id=alert.account_id,
                alert_id=alert.id,
                transport=TRANSPORT_EMAIL,
                attempt_number=1,
                status=DELIVERY_ATTEMPT_DELIVERED if success else DELIVERY_ATTEMPT_FAILED,
            )
        )

    alert.status = STATUS_ALERT_DELIVERED
    await session.flush()
    return Delivered(alert_id=alert.id)
