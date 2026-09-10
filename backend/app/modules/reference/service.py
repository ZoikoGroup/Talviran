"""Reference-module business logic: paginated reads, gated through the PDP
before any query runs — this is what ENG-ARCH-003's P0 exit criterion means
by "a rights-aware data access path is demonstrated end to end," even
though there's no real instrument data seeded yet.

Reference/master data (this registry) is Talvrin's own canonical data, not
licensed vendor content — unlike market observations or documents, so it
doesn't have a per-vendor rights_profile. It's still run through the rights
engine (not skipped) via a platform-owned rights profile representing "our
own open reference data," so the enforcement path is real and identical to
how a licensed resource will be gated later, rather than a special-cased
bypass for this one resource type.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, TalvrinAPIError
from app.core.pagination import Page, paginate_by_id
from app.modules.policy.pdp import PolicyContext, evaluate
from app.modules.reference.models import Instrument, Issuer
from app.modules.rights.models import RightsProfile

# No real auth/session-derived jurisdiction resolution exists yet
# (SEC-001 hardening is P2) — hardcoded to the launch jurisdiction until an
# api.deps auth dependency can supply a real one.
_DEV_JURISDICTION = "GB"

# Names the platform-owned rights profile for Talvrin's own reference data,
# seeded by scripts/seed_dev.py — deliberately NOT None, so this exercises
# the exact same evaluate_action() code path a licensed vendor resource
# will use later, rather than skipping the rights stage for "our own" data.
REFERENCE_RIGHTS_PROFILE_CODE = "platform.reference_data"


async def _enforce_read_access(session: AsyncSession, capability_code: str) -> None:
    rights_profile_id = (
        await session.execute(
            select(RightsProfile.id).where(RightsProfile.code == REFERENCE_RIGHTS_PROFILE_CODE)
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


async def list_issuers(
    session: AsyncSession, *, cursor: str | None, limit: int
) -> Page[Issuer]:
    await _enforce_read_access(session, "reference.issuers.read")
    stmt = select(Issuer)
    return await paginate_by_id(
        session, stmt, Issuer.id, cursor=cursor, limit=limit, get_id=lambda row: row.id
    )


async def list_instruments(
    session: AsyncSession, *, cursor: str | None, limit: int
) -> Page[Instrument]:
    await _enforce_read_access(session, "reference.instruments.read")
    stmt = select(Instrument)
    return await paginate_by_id(
        session, stmt, Instrument.id, cursor=cursor, limit=limit, get_id=lambda row: row.id
    )
