"""Seeds the minimum governance rows needed for the read endpoints to
PERMIT instead of fail closed by (correct) default. Run with:

    uv run python -m scripts.seed_dev

Idempotent: safe to run repeatedly against the same dev database — every
insert is guarded by a "does this already exist" check first.

Does NOT seed any instrument/issuer data yet — real gilt data lands in P1
(week 7+) via the DMO connector. This only seeds the governance layer
(capability status, jurisdiction activation, the platform reference-data
rights profile) so the currently-empty reference endpoints return `200`
with an empty page instead of `403 POLICY_BLOCKED`.
"""

import asyncio
import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.reference.service import REFERENCE_RIGHTS_PROFILE_CODE
from app.modules.rights.models import RightsGrant, RightsProfile

_JURISDICTION = "GB"
_CAPABILITIES = ["reference.issuers.read", "reference.instruments.read"]


async def _seed_capability_statuses(session: AsyncSession) -> None:
    for code in _CAPABILITIES:
        existing = (
            await session.execute(
                select(CapabilityStatus).where(
                    CapabilityStatus.capability_code == code,
                    CapabilityStatus.jurisdiction_code.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                CapabilityStatus(capability_code=code, jurisdiction_code=None, status="AVAILABLE")
            )
            print(f"  + capability_status {code} -> AVAILABLE")


async def _seed_activation_record(session: AsyncSession) -> None:
    existing = (
        await session.execute(
            select(ActivationRecord).where(
                ActivationRecord.jurisdiction_code == _JURISDICTION,
                ActivationRecord.status == "ACTIVE",
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ActivationRecord(
                jurisdiction_code=_JURISDICTION,
                operating_entity="Talvrin Dev",
                status="ACTIVE",
                effective_from=dt.datetime.now(dt.UTC) - dt.timedelta(days=1),
                effective_to=None,
            )
        )
        print(f"  + activation_record {_JURISDICTION} -> ACTIVE")


async def _seed_reference_rights_profile(session: AsyncSession) -> None:
    profile = (
        await session.execute(
            select(RightsProfile).where(RightsProfile.code == REFERENCE_RIGHTS_PROFILE_CODE)
        )
    ).scalar_one_or_none()
    if profile is None:
        profile = RightsProfile(code=REFERENCE_RIGHTS_PROFILE_CODE, status="ACTIVE")
        session.add(profile)
        await session.flush()
        print(f"  + rights_profile {REFERENCE_RIGHTS_PROFILE_CODE} -> ACTIVE")

    grant = (
        await session.execute(
            select(RightsGrant).where(
                RightsGrant.rights_profile_id == profile.id,
                RightsGrant.action == "retrieve",
            )
        )
    ).scalar_one_or_none()
    if grant is None:
        session.add(
            RightsGrant(
                rights_profile_id=profile.id, action="retrieve", permission_state="ALLOW"
            )
        )
        print(f"  + rights_grant {REFERENCE_RIGHTS_PROFILE_CODE}.retrieve -> ALLOW")


async def seed() -> None:
    factory = get_session_factory()
    async with factory() as session:
        await _seed_capability_statuses(session)
        await _seed_activation_record(session)
        await _seed_reference_rights_profile(session)
        await session.commit()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
