"""Alert delivery (MON-001 §14) - this slice's one transport, IN_APP: an
alert is "delivered" the moment it's visible through
GET /api/v1/alerts, so delivering it is just recording that fact, not
calling any external provider. Real push transports (email/SMS/webhook)
are a separate, later slice - see monitoring/models.py's docstring for
why QUEUED/retry bookkeeping aren't modelled yet either (IN_APP either
succeeds synchronously or the whole request fails; there is no
in-between state).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.monitoring.models import (
    DELIVERY_ATTEMPT_DELIVERED,
    STATUS_ALERT_DELIVERED,
    STATUS_ALERT_SUPPRESSED,
    TRANSPORT_IN_APP,
    Alert,
    AlertDeliveryAttempt,
)


@dataclass(frozen=True)
class DeliverySkipped:
    reason: str


@dataclass(frozen=True)
class Delivered:
    alert_id: uuid.UUID


async def deliver_alert(
    session: AsyncSession, *, alert_id: uuid.UUID
) -> Delivered | DeliverySkipped:
    """Idempotent: re-delivering an already-DELIVERED alert is a no-op, not
    a second attempt row - IN_APP visibility doesn't change on replay.
    """
    alert = await session.get(Alert, alert_id)
    if alert is None:
        return DeliverySkipped(reason=f"no alert {alert_id}")

    if alert.status == STATUS_ALERT_DELIVERED:
        return Delivered(alert_id=alert.id)
    if alert.status == STATUS_ALERT_SUPPRESSED:
        return DeliverySkipped(reason=f"alert {alert_id} is suppressed, not deliverable")

    session.add(
        AlertDeliveryAttempt(
            account_id=alert.account_id,
            alert_id=alert.id,
            transport=TRANSPORT_IN_APP,
            attempt_number=1,
            status=DELIVERY_ATTEMPT_DELIVERED,
        )
    )
    alert.status = STATUS_ALERT_DELIVERED
    await session.flush()
    return Delivered(alert_id=alert.id)
