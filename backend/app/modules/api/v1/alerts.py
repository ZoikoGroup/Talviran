"""GET /api/v1/alerts (P3) - the first user-facing surface for monitoring
output: a signed-in user's own alerts, RLS-scoped to their account and
PDP-gated like every other response path. Authenticated (IdentityDep),
unlike instruments.py/calculations.py: alerts are per-account data, not
platform-wide reference/calculation output.
"""

import uuid

from fastapi import APIRouter, Query

from app.core.errors import ErrorCode, TalvrinAPIError
from app.core.pagination import PageOut
from app.modules.api.v1.deps import IdentityDep, SessionDep
from app.modules.monitoring import delivery, service
from app.modules.monitoring.schemas import AlertOut, TriggerAlertIn

router = APIRouter(prefix="/alerts", tags=["monitoring"])


def _not_found() -> TalvrinAPIError:
    return TalvrinAPIError(code=ErrorCode.NOT_FOUND, message="Not found.")


@router.get("", response_model=PageOut[AlertOut])
async def list_alerts(
    session: SessionDep,
    identity: IdentityDep,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> PageOut[AlertOut]:
    page = await service.list_my_alerts(
        session,
        principal_id=identity.principal_id,
        account_id=identity.account_id,
        cursor=cursor,
        limit=limit,
    )
    return PageOut[AlertOut](
        items=[AlertOut.model_validate(row) for row in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: uuid.UUID, session: SessionDep, identity: IdentityDep
) -> AlertOut:
    alert = await service.get_my_alert(
        session,
        alert_id=alert_id,
        principal_id=identity.principal_id,
        account_id=identity.account_id,
    )
    if alert is None:
        raise _not_found()
    return AlertOut.model_validate(alert)


@router.post("/trigger")
async def trigger_and_dispatch_alert(
    body: TriggerAlertIn,
    identity: IdentityDep,
) -> dict[str, str | bool]:
    """Receives touched alert from active surveillance, dispatches email to user account,
    and returns delivery confirmation.
    """
    recipient = body.recipient_email or identity.email
    email_dispatched = False
    if recipient:
        email_dispatched = delivery.send_market_alert_email(
            recipient_email=recipient,
            asset_symbol=body.asset_symbol,
            asset_name=body.asset_name,
            threshold_value=body.threshold_value,
            observed_value=body.observed_value,
            predicate=body.predicate,
        )

    return {
        "status": "triggered",
        "email_dispatched": email_dispatched,
        "recipient": recipient,
        "asset_symbol": body.asset_symbol,
    }
