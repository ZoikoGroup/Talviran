"""Real-DB PDP tests — proves the precedence walk (kill-switch -> capability
status -> jurisdiction activation -> rights) against actual governance rows,
and that every verdict is durably logged to governance.policy_decision.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.policy.allowed_output_type import AllowedOutputType
from app.modules.policy.models import ActivationRecord, CapabilityStatus, KillSwitch
from app.modules.policy.models import PolicyDecision as PolicyDecisionRow
from app.modules.policy.pdp import PolicyContext, evaluate
from app.modules.rights.models import RightsGrant, RightsProfile

CAPABILITY = "research.gilt_facts"
JURISDICTION = "GB"


def _ctx(**overrides: object) -> PolicyContext:
    defaults: dict[str, object] = {
        "principal_id": None,
        "account_id": None,
        "jurisdiction_code": JURISDICTION,
        "capability_code": CAPABILITY,
        "requested_output_type": AllowedOutputType.FACTUAL_EVIDENCE,
    }
    defaults.update(overrides)
    return PolicyContext(**defaults)  # type: ignore[arg-type]


async def _activate_capability(session: AsyncSession) -> None:
    now = dt.datetime.now(dt.UTC)
    session.add(
        CapabilityStatus(capability_code=CAPABILITY, jurisdiction_code=None, status="AVAILABLE")
    )
    session.add(
        ActivationRecord(
            jurisdiction_code=JURISDICTION,
            operating_entity="Talvrin UK Ltd",
            status="ACTIVE",
            effective_from=now - dt.timedelta(days=1),
            effective_to=None,
        )
    )
    await session.flush()


async def test_denies_when_capability_is_unregistered(db_session: AsyncSession) -> None:
    decision = await evaluate(db_session, _ctx())
    assert decision.is_permit is False
    assert decision.reason_codes == ["CAPABILITY_UNKNOWN"]


async def test_denies_when_capability_registered_but_not_available(
    db_session: AsyncSession,
) -> None:
    db_session.add(
        CapabilityStatus(capability_code=CAPABILITY, jurisdiction_code=None, status="RESTRICTED")
    )
    await db_session.flush()

    decision = await evaluate(db_session, _ctx())
    assert decision.is_permit is False
    assert decision.reason_codes == ["CAPABILITY_UNAVAILABLE"]


async def test_denies_when_jurisdiction_not_activated(db_session: AsyncSession) -> None:
    db_session.add(
        CapabilityStatus(capability_code=CAPABILITY, jurisdiction_code=None, status="AVAILABLE")
    )
    await db_session.flush()
    # No ActivationRecord at all for JURISDICTION.

    decision = await evaluate(db_session, _ctx())
    assert decision.is_permit is False
    assert decision.reason_codes == ["JURISDICTION_NOT_ACTIVATED"]


async def test_denies_when_jurisdiction_code_missing(db_session: AsyncSession) -> None:
    await _activate_capability(db_session)

    decision = await evaluate(db_session, _ctx(jurisdiction_code=None))
    assert decision.is_permit is False
    assert decision.reason_codes == ["JURISDICTION_UNRESOLVED"]


async def test_kill_switch_denies_even_when_everything_else_permits(
    db_session: AsyncSession,
) -> None:
    await _activate_capability(db_session)
    db_session.add(KillSwitch(code=CAPABILITY, is_active=True))
    await db_session.flush()

    decision = await evaluate(db_session, _ctx())
    assert decision.is_permit is False
    assert decision.reason_codes == ["KILL_SWITCH_ACTIVE"]


async def test_permits_when_capability_and_jurisdiction_are_clear(
    db_session: AsyncSession,
) -> None:
    await _activate_capability(db_session)

    decision = await evaluate(db_session, _ctx())
    assert decision.is_permit is True
    assert decision.allowed_output_type == AllowedOutputType.FACTUAL_EVIDENCE


async def test_rights_restricted_denies_after_policy_stages_pass(
    db_session: AsyncSession,
) -> None:
    await _activate_capability(db_session)
    profile = RightsProfile(code="dmo-gilts-pdp-test", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    db_session.add(
        RightsGrant(rights_profile_id=profile.id, action="ai", permission_state="DENY")
    )
    await db_session.flush()

    decision = await evaluate(
        db_session, _ctx(rights_action="ai", rights_profile_id=profile.id)
    )
    assert decision.is_permit is False
    assert decision.reason_codes == ["RIGHTS_RESTRICTED"]


async def test_every_verdict_is_logged_to_policy_decision(db_session: AsyncSession) -> None:
    await evaluate(db_session, _ctx())  # denies: no capability registered
    await _activate_capability(db_session)
    await evaluate(db_session, _ctx())  # permits
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(PolicyDecisionRow).order_by(PolicyDecisionRow.evaluated_at)
        )
    ).scalars().all()

    assert [row.decision for row in rows] == ["DENY", "PERMIT"]
    assert rows[0].reason_codes == ["CAPABILITY_UNKNOWN"]
    assert rows[1].allowed_output_type == AllowedOutputType.FACTUAL_EVIDENCE.value
