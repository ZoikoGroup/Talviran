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
from app.modules.monitoring import service
from app.modules.monitoring.schemas import AlertOut

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


# A POST /trigger endpoint used to live here: it accepted a caller-supplied
# asset_symbol/threshold_value/observed_value/recipient_email with no
# verification against any real MonitoringRule or Alert row, and
# unconditionally sent a real Resend email captioned "Verified threshold
# event... using an entitled, validated price observation" - a false claim
# every time, to any recipient_email the caller named. Its only caller
# anywhere in the codebase was the frontend's fabricated client-side
# crossing-detection (MonitoringPage.tsx, removed 2026-11-10 UAT gap
# analysis G11 remediation). The genuine delivery path - monitoring.
# delivery.deliver_alert, driven entirely by a real Alert row the real
# evaluator produced from a real rule + real observation - is untouched
# and remains the only way an alert email is ever sent.
