"""RIGHTS-001's action vocabulary, evaluated per-action against a
RightsProfile — never a single can_use boolean. Every caller must name the
specific action it's performing; there is no "check if allowed" shortcut
that skips saying which action.
"""

import uuid
from enum import StrEnum
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rights.models import RightsGrant, RightsProfile

RightsAction = Literal[
    "retrieve",
    "store",
    "cache",
    "index",
    "embed",
    "ai",
    "display",
    "export",
    "redistribute",
]

# States that actually permit the action. Every other value — including
# DENY, CONDITIONAL, LIMITED, UNKNOWN, EXPIRED, or anything unrecognized —
# denies. RIGHTS-001 RG-03 is explicit that UNKNOWN and EXPIRED are DENY,
# not "treat as pending."
_ALLOWING_STATES = frozenset({"ALLOW"})


class RightsDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


async def evaluate_action(
    session: AsyncSession,
    action: RightsAction,
    rights_profile_id: uuid.UUID | None,
) -> RightsDecision:
    """Fail-closed on every branch: no profile id, missing profile, an
    inactive profile, a missing grant for this specific action, or a grant
    whose permission_state isn't ALLOW all resolve to DENY.
    """
    if rights_profile_id is None:
        return RightsDecision.DENY

    profile = await session.get(RightsProfile, rights_profile_id)
    if profile is None or profile.status != "ACTIVE":
        return RightsDecision.DENY

    grant = (
        await session.execute(
            select(RightsGrant).where(
                RightsGrant.rights_profile_id == rights_profile_id,
                RightsGrant.action == action,
            )
        )
    ).scalar_one_or_none()

    if grant is None or grant.permission_state not in _ALLOWING_STATES:
        return RightsDecision.DENY

    return RightsDecision.ALLOW
