"""Real-DB rights engine tests — proves evaluate_action's fail-closed matrix
against actual rights_profile/rights_grant rows, not just the None
short-circuit already covered in tests/unit.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rights.engine import RightsDecision, evaluate_action
from app.modules.rights.models import RightsGrant, RightsProfile


async def test_unknown_profile_id_denies(db_session: AsyncSession) -> None:
    decision = await evaluate_action(db_session, "retrieve", uuid.uuid4())
    assert decision is RightsDecision.DENY


async def test_inactive_profile_denies_even_with_allow_grant(db_session: AsyncSession) -> None:
    profile = RightsProfile(code="dmo-gilts-inactive", status="DRAFT")
    db_session.add(profile)
    await db_session.flush()
    db_session.add(
        RightsGrant(rights_profile_id=profile.id, action="retrieve", permission_state="ALLOW")
    )
    await db_session.flush()

    decision = await evaluate_action(db_session, "retrieve", profile.id)
    assert decision is RightsDecision.DENY


async def test_active_profile_missing_grant_for_action_denies(db_session: AsyncSession) -> None:
    profile = RightsProfile(code="dmo-gilts-partial", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    db_session.add(
        RightsGrant(rights_profile_id=profile.id, action="retrieve", permission_state="ALLOW")
    )
    await db_session.flush()

    # "export" was never granted at all for this profile.
    decision = await evaluate_action(db_session, "export", profile.id)
    assert decision is RightsDecision.DENY


async def test_active_profile_with_allow_grant_permits(db_session: AsyncSession) -> None:
    profile = RightsProfile(code="dmo-gilts-active", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    db_session.add(
        RightsGrant(rights_profile_id=profile.id, action="display", permission_state="ALLOW")
    )
    await db_session.flush()

    decision = await evaluate_action(db_session, "display", profile.id)
    assert decision is RightsDecision.ALLOW


async def test_non_allow_permission_states_all_deny(db_session: AsyncSession) -> None:
    profile = RightsProfile(code="dmo-gilts-states", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()

    for action, state in [
        ("retrieve", "DENY"),
        ("store", "CONDITIONAL"),
        ("cache", "LIMITED"),
        ("index", "UNKNOWN"),
        ("embed", "EXPIRED"),
    ]:
        db_session.add(
            RightsGrant(rights_profile_id=profile.id, action=action, permission_state=state)
        )
    await db_session.flush()

    for action, _ in [
        ("retrieve", "DENY"),
        ("store", "CONDITIONAL"),
        ("cache", "LIMITED"),
        ("index", "UNKNOWN"),
        ("embed", "EXPIRED"),
    ]:
        decision = await evaluate_action(db_session, action, profile.id)  # type: ignore[arg-type]
        assert decision is RightsDecision.DENY, f"{action} should deny under a non-ALLOW state"
