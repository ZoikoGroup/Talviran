"""Read access to a signed-in user's own alerts (GET /api/v1/alerts) - the
first user-facing surface for anything monitoring produces. RLS already
scopes every query here to the caller's own account (alert carries
account_id and FORCE ROW LEVEL SECURITY, same as research.message); this
adds the PDP gate on top, exactly like every other response path
(evidence/service.py, calculation/service.py) - RLS restricts WHICH rows
exist for this account, the PDP decides whether this capability is even
switched on at all (kill-switch/jurisdiction/rights precedence).

A GET-only endpoint never has another natural commit point in this
project's per-request session lifecycle (core/db.get_session's own
docstring: "callers commit explicitly") - _enforce_read_access commits
right after evaluate() so the PDP's own audit-log write persists
regardless of whether the request goes on to succeed, mirroring
calculation/service.py's identical need for the identical reason.

Unlike calculation_result, alert is RLS-scoped - and set_config(...,
is_local=true)'s GUC is transaction-local (migration 0002's own reasoning
for using it at all). Committing ends that transaction, which silently
clears app.account_id along with it: the SELECT that follows would run
with no RLS context and match nothing, not "everything" or "an error" -
the single most dangerous failure mode for GUC-based RLS applies here
just as much as to a pooled connection reused across requests. Re-
applying the context immediately after the commit, in the same
already-known account/principal, is what keeps a PERMIT actually able to
read the rows RLS itself allows.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, TalvrinAPIError
from app.core.pagination import Page, paginate_by_id
from app.modules.identity.service import apply_rls_context
from app.modules.monitoring.models import Alert
from app.modules.policy.allowed_output_type import AllowedOutputType
from app.modules.policy.pdp import PolicyContext, evaluate

_DEV_JURISDICTION = "GB"
MONITORING_ALERTS_READ_CAPABILITY = "monitoring.alerts.read"


async def _enforce_read_access(
    session: AsyncSession, *, principal_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    ctx = PolicyContext(
        principal_id=principal_id,
        account_id=account_id,
        jurisdiction_code=_DEV_JURISDICTION,
        capability_code=MONITORING_ALERTS_READ_CAPABILITY,
        requested_output_type=AllowedOutputType.USER_RULE_ALERT,
    )
    decision = await evaluate(session, ctx)
    await session.commit()
    await apply_rls_context(session, account_id=account_id, principal_id=principal_id)

    if not decision.is_permit:
        raise TalvrinAPIError(
            ErrorCode.POLICY_BLOCKED,
            "Access to this resource is not currently permitted.",
            details={"reason_codes": decision.reason_codes},
        )


async def list_my_alerts(
    session: AsyncSession,
    *,
    principal_id: uuid.UUID,
    account_id: uuid.UUID,
    cursor: str | None,
    limit: int,
) -> Page[Alert]:
    await _enforce_read_access(session, principal_id=principal_id, account_id=account_id)
    stmt = select(Alert)
    return await paginate_by_id(
        session, stmt, Alert.id, cursor=cursor, limit=limit, get_id=lambda row: row.id
    )


async def get_my_alert(
    session: AsyncSession, *, alert_id: uuid.UUID, principal_id: uuid.UUID, account_id: uuid.UUID
) -> Alert | None:
    await _enforce_read_access(session, principal_id=principal_id, account_id=account_id)
    return await session.get(Alert, alert_id)
