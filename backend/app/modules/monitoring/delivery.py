"""Alert delivery (MON-001 §14) - transports: IN_APP and EMAIL via Resend."""

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

        html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Talvrin Market Alert</title>
</head>
<body style="margin: 0; padding: 24px; background-color: #0b0f19; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0;">
  <div style="max-width: 560px; margin: 0 auto; background-color: #111827; border: 1px solid #1f2937; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
    <div style="padding: 24px 28px; border-bottom: 1px solid #1f2937; background: linear-gradient(180deg, #182234 0%, #111827 100%);">
      <div style="display: flex; align-items: center; justify-content: space-between;">
        <span style="font-size: 18px; font-weight: 700; letter-spacing: -0.02em; color: #ffffff;">TALVRIN</span>
        <span style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; background: rgba(99, 102, 241, 0.2); color: #818cf8; padding: 4px 10px; border-radius: 9999px; border: 1px solid rgba(99, 102, 241, 0.3);">
          Objective Alert
        </span>
      </div>
      <p style="margin: 8px 0 0; font-size: 12px; color: #94a3b8;">
        The Evidence Layer for Public Markets
      </p>
    </div>

    <div style="padding: 28px;">
      <h1 style="margin: 0 0 16px; font-size: 19px; font-weight: 600; color: #f8fafc; line-height: 1.3;">
        Market Trigger Activated
      </h1>
      <p style="margin: 0 0 20px; font-size: 13.5px; line-height: 1.5; color: #94a3b8;">
        An automated rule surveillance trigger on your Talvrin account has executed.
      </p>

      <div style="background-color: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 18px 20px; margin-bottom: 24px;">
        <div style="margin-bottom: 14px;">
          <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-bottom: 4px;">Asset / Metric</div>
          <div style="font-size: 15px; font-weight: 600; color: #f1f5f9;">{metric_str}</div>
        </div>

        <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
          <tr>
            <td style="padding: 10px 0; border-top: 1px solid #1e293b; width: 50%;">
              <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b;">Target Threshold</div>
              <div style="font-size: 15px; font-weight: 600; color: #cbd5e1; margin-top: 2px;">{thresh_str}</div>
            </td>
            <td style="padding: 10px 0; border-top: 1px solid #1e293b; width: 50%;">
              <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b;">Observed Value</div>
              <div style="font-size: 15px; font-weight: 700; color: #38bdf8; margin-top: 2px;">{obs_str}</div>
            </td>
          </tr>
        </table>
      </div>

      <div style="display: inline-block; padding: 6px 12px; background-color: #1e293b; border-radius: 6px; font-size: 12px; color: #94a3b8;">
        Trigger Timestamp: <strong style="color: #cbd5e1;">{time_str}</strong>
      </div>
    </div>

    <div style="padding: 18px 28px; background-color: #0c1220; border-top: 1px solid #1f2937; text-align: left;">
      <p style="margin: 0 0 6px; font-size: 11px; color: #64748b; line-height: 1.5;">
        You received this notification because your account configured an alert for {metric_str}.
      </p>
      <p style="margin: 0; font-size: 10.5px; color: #475569; line-height: 1.4;">
        Talvrin delivers factual market observations and deterministic triggers. This transmission does not constitute financial, investment, or trading advice.
      </p>
    </div>
  </div>
</body>
</html>"""

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
