"""POST/GET /api/v1/monitoring-rules (P3) - the missing half of the alerts
surface: alerts.py already lets a signed-in user read what fired; this lets
them define what to watch. Same PDP/RLS shape as alerts.py throughout.
Rules were previously only creatable by a script or a test fixture.
"""

import uuid

from fastapi import APIRouter, Query, status

from app.core.errors import ErrorCode, TalvrinAPIError
from app.core.pagination import PageOut
from app.modules.api.v1.deps import IdentityDep, SessionDep
from app.modules.monitoring import service
from app.modules.monitoring.models import MonitoringRuleVersion
from app.modules.monitoring.schemas import RuleIn, RuleOut

router = APIRouter(prefix="/monitoring-rules", tags=["monitoring"])


def _not_found() -> TalvrinAPIError:
    return TalvrinAPIError(code=ErrorCode.NOT_FOUND, message="Not found.")


def _rejected(reason: str) -> TalvrinAPIError:
    return TalvrinAPIError(code=ErrorCode.VALIDATION_ERROR, message=reason)


def _rule_out(version: MonitoringRuleVersion) -> RuleOut:
    return RuleOut(
        id=version.rule_id,
        status=version.status,
        subject_type=version.subject_type,
        subject_id=version.subject_id,
        metric_id=version.metric_id,
        predicate=version.predicate,
        threshold_value=version.threshold_value,
        rearm_threshold=version.rearm_threshold,
        debounce_seconds=version.debounce_seconds,
        effective_from=version.effective_from,
        created_at=version.created_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RuleOut)
async def create_rule(body: RuleIn, session: SessionDep, identity: IdentityDep) -> RuleOut:
    result = await service.create_rule(
        session,
        principal_id=identity.principal_id,
        account_id=identity.account_id,
        metric_id=body.metric_id,
        predicate=body.predicate,
        threshold_value=body.threshold_value,
        instrument_isin=body.instrument_isin,
        tenor_years=body.tenor_years,
        rearm_threshold=body.rearm_threshold,
        debounce_seconds=body.debounce_seconds,
    )
    if isinstance(result, service.RuleRejected):
        raise _rejected(result.reason)
    await session.commit()
    return _rule_out(result)


@router.get("", response_model=PageOut[RuleOut])
async def list_rules(
    session: SessionDep,
    identity: IdentityDep,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> PageOut[RuleOut]:
    page = await service.list_my_rules(
        session,
        principal_id=identity.principal_id,
        account_id=identity.account_id,
        cursor=cursor,
        limit=limit,
    )
    return PageOut[RuleOut](
        items=[_rule_out(row) for row in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/{rule_id}", response_model=RuleOut)
async def get_rule(rule_id: uuid.UUID, session: SessionDep, identity: IdentityDep) -> RuleOut:
    version = await service.get_my_rule(
        session,
        rule_id=rule_id,
        principal_id=identity.principal_id,
        account_id=identity.account_id,
    )
    if version is None:
        raise _not_found()
    return _rule_out(version)
