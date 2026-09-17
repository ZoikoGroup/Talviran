"""Calculation-module reads (P2): calculation_result was only ever
surfaced indirectly before this - embedded in a POST /api/v1/research
reply's fact table. This gives it a real, directly-queryable read path,
gated through the PDP exactly like reference/service.py's instruments and
issuers endpoints (same platform-owned-rights-profile pattern, not a
special-cased bypass).

calculation_result isn't account-scoped (no RLS - same reasoning as
market.accepted_fact: it's platform-wide reconciled/computed truth, not
per-tenant data), so this mirrors reference/service.py's unauthenticated,
PDP-gated shape rather than research/service.py's per-account RLS shape.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, TalvrinAPIError
from app.core.pagination import Page, paginate_by_id
from app.modules.calculation.models import CalculationInput, CalculationResult
from app.modules.policy.pdp import PolicyContext, evaluate
from app.modules.rights.models import RightsProfile

_DEV_JURISDICTION = "GB"

# calculation_result is Talvrin's own computed output, not reference/master
# data or licensed vendor content - a distinct category from
# reference.service's REFERENCE_RIGHTS_PROFILE_CODE, so it gets its own
# platform-owned rights profile rather than borrowing that module's.
CALCULATION_RIGHTS_PROFILE_CODE = "platform.calculation_data"


async def _enforce_read_access(session: AsyncSession, capability_code: str) -> None:
    rights_profile_id = (
        await session.execute(
            select(RightsProfile.id).where(RightsProfile.code == CALCULATION_RIGHTS_PROFILE_CODE)
        )
    ).scalar_one_or_none()

    ctx = PolicyContext(
        principal_id=None,
        account_id=None,
        jurisdiction_code=_DEV_JURISDICTION,
        capability_code=capability_code,
        rights_action="retrieve",
        rights_profile_id=rights_profile_id,
    )
    decision = await evaluate(session, ctx)
    await session.commit()

    if not decision.is_permit:
        raise TalvrinAPIError(
            ErrorCode.POLICY_BLOCKED,
            "Access to this resource is not currently permitted.",
            details={"reason_codes": decision.reason_codes},
        )


async def list_calculation_results(
    session: AsyncSession,
    *,
    subject_id: uuid.UUID | None,
    metric_id: str | None,
    cursor: str | None,
    limit: int,
) -> Page[CalculationResult]:
    await _enforce_read_access(session, "calculation.results.read")
    stmt = select(CalculationResult).where(CalculationResult.status == "ACTIVE")
    if subject_id is not None:
        stmt = stmt.where(CalculationResult.subject_id == subject_id)
    if metric_id is not None:
        stmt = stmt.where(CalculationResult.metric_id == metric_id)
    return await paginate_by_id(
        session, stmt, CalculationResult.id, cursor=cursor, limit=limit,
        get_id=lambda row: row.id,
    )


async def get_calculation_result(
    session: AsyncSession, *, result_id: uuid.UUID
) -> tuple[CalculationResult, list[CalculationInput]] | None:
    await _enforce_read_access(session, "calculation.results.read")
    result = await session.get(CalculationResult, result_id)
    if result is None:
        return None
    inputs = (
        await session.execute(
            select(CalculationInput).where(CalculationInput.calculation_result_id == result_id)
        )
    ).scalars().all()
    return result, list(inputs)
