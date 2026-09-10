"""The Policy Decision Point — POL-001's server-side gate that every
protected request must pass through before business logic runs. Fixed
precedence order (kill-switches -> capability status -> jurisdiction policy
-> data rights -> commercial entitlement -> feature flags): a later stage
can never widen an earlier stage's DENY, and any missing/ambiguous/erroring
input at any stage denies rather than guesses (fail-closed, POL-001 fail-
closed doctrine / D-10).

Commercial entitlement and feature-flag stages are deliberate stubs — no
`commercial` schema tables or flag store exist yet (that's P5 scope) — so
they always permit for now. Every other stage is real, not a placeholder.
"""

import datetime as dt
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import get_request_id
from app.modules.policy.allowed_output_type import AllowedOutputType
from app.modules.policy.models import ActivationRecord, CapabilityStatus, KillSwitch
from app.modules.policy.models import PolicyDecision as PolicyDecisionRow
from app.modules.rights.engine import RightsAction, RightsDecision, evaluate_action


@dataclass(frozen=True)
class PolicyContext:
    """Everything the PDP needs to decide one request, built once per
    request rather than assembled piecemeal across the call chain."""

    principal_id: uuid.UUID | None
    account_id: uuid.UUID | None
    jurisdiction_code: str | None
    capability_code: str
    requested_output_type: AllowedOutputType | None = None
    rights_action: RightsAction | None = None
    rights_profile_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Decision:
    is_permit: bool
    reason_codes: list[str]
    allowed_output_type: AllowedOutputType | None = None
    obligations: dict[str, str] = field(default_factory=dict)


def _deny(*reason_codes: str) -> Decision:
    return Decision(is_permit=False, reason_codes=list(reason_codes))


async def evaluate(session: AsyncSession, ctx: PolicyContext) -> Decision:
    try:
        decision = await _evaluate_uncaught(session, ctx)
    except Exception:
        # Anything unexpected (DB unreachable, malformed row, a bug in a
        # check below) fails closed — an exception must never surface
        # upstream as an implicit permit.
        decision = _deny("PDP_EVALUATION_ERROR")

    await _log_decision(session, ctx, decision)
    return decision


async def _evaluate_uncaught(session: AsyncSession, ctx: PolicyContext) -> Decision:
    kill = await _check_kill_switches(session, ctx)
    if kill is not None:
        return kill

    capability = await _check_capability_status(session, ctx)
    if capability is not None:
        return capability

    jurisdiction = await _check_jurisdiction_activation(session, ctx)
    if jurisdiction is not None:
        return jurisdiction

    if ctx.rights_action is not None:
        rights_decision = await evaluate_action(session, ctx.rights_action, ctx.rights_profile_id)
        if rights_decision is RightsDecision.DENY:
            return _deny("RIGHTS_RESTRICTED")

    # Commercial entitlement, feature flags: stubs, see module docstring.

    return Decision(
        is_permit=True,
        reason_codes=[],
        allowed_output_type=ctx.requested_output_type,
    )


async def _check_kill_switches(session: AsyncSession, ctx: PolicyContext) -> Decision | None:
    switch = (
        await session.execute(select(KillSwitch).where(KillSwitch.code == ctx.capability_code))
    ).scalar_one_or_none()
    if switch is not None and switch.is_active:
        return _deny("KILL_SWITCH_ACTIVE")
    return None


async def _check_capability_status(session: AsyncSession, ctx: PolicyContext) -> Decision | None:
    # Jurisdiction-specific row takes precedence over a jurisdiction-neutral
    # one when both exist for the same capability_code.
    rows = (
        await session.execute(
            select(CapabilityStatus).where(CapabilityStatus.capability_code == ctx.capability_code)
        )
    ).scalars().all()

    specific = next((r for r in rows if r.jurisdiction_code == ctx.jurisdiction_code), None)
    general = next((r for r in rows if r.jurisdiction_code is None), None)
    status_row = specific or general

    if status_row is None:
        # No governed capability_status row for this code at all: an
        # unregistered capability is not "assume available" — it's DENY.
        return _deny("CAPABILITY_UNKNOWN")
    if status_row.status != "AVAILABLE":
        return _deny("CAPABILITY_UNAVAILABLE")
    return None


async def _check_jurisdiction_activation(
    session: AsyncSession, ctx: PolicyContext
) -> Decision | None:
    if ctx.jurisdiction_code is None:
        return _deny("JURISDICTION_UNRESOLVED")

    now = dt.datetime.now(dt.UTC)
    rows = (
        await session.execute(
            select(ActivationRecord).where(
                ActivationRecord.jurisdiction_code == ctx.jurisdiction_code,
                ActivationRecord.status == "ACTIVE",
            )
        )
    ).scalars().all()

    is_activated = any(
        row.effective_from <= now and (row.effective_to is None or row.effective_to > now)
        for row in rows
    )
    if not is_activated:
        return _deny("JURISDICTION_NOT_ACTIVATED")
    return None


async def _log_decision(session: AsyncSession, ctx: PolicyContext, decision: Decision) -> None:
    """Every verdict is logged, permit or deny — this is what lets a
    regulator-response reconstruction happen later. Added to the session,
    not committed here — the caller's transaction boundary owns that, same
    convention as app.modules.audit.service.record_event.
    """
    session.add(
        PolicyDecisionRow(
            request_id=get_request_id(),
            principal_id=ctx.principal_id,
            account_id=ctx.account_id,
            decision="PERMIT" if decision.is_permit else "DENY",
            reason_codes=decision.reason_codes,
            allowed_output_type=(
                decision.allowed_output_type.value if decision.allowed_output_type else None
            ),
            obligations=decision.obligations or None,
        )
    )
