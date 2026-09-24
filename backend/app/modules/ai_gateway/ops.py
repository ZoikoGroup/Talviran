"""AI-001 A5 ("operations"): read-only health/status reporting and the
kill-switch activate/deactivate actions AI-001 §27's operational
requirements name - see scripts/ai_gateway_ops.py, the CLI this module
backs. Script-based, not an admin API endpoint: no admin/ops role model
exists anywhere in this codebase yet (kill switches are otherwise only
ever touched by direct DB writes in scripts/tests), matching the same
convention scripts/approve_calculation_spec.py and
scripts/seed_ai_gateway.py already established - not a new precedent,
and not something to bolt a speculative auth layer onto here.
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_gateway.models import (
    KILL_SWITCH_GLOBAL_CODE,
    AIModel,
    AIModelExecution,
    AIProvider,
    kill_switch_model_code,
    kill_switch_provider_code,
)
from app.modules.policy.models import KillSwitch


@dataclass(frozen=True)
class RouteHealth:
    task_type: str
    priority: int
    provider_code: str
    provider_status: str
    model_key: str
    model_status: str
    provider_killswitched: bool
    model_killswitched: bool
    recent_executions: int
    recent_errors: int


@dataclass(frozen=True)
class GatewayHealth:
    global_killswitch_active: bool
    routes: list[RouteHealth]


async def _killswitch_active(session: AsyncSession, *, code: str) -> bool:
    switch = (
        await session.execute(select(KillSwitch).where(KillSwitch.code == code))
    ).scalar_one_or_none()
    return switch is not None and switch.is_active


async def get_health(session: AsyncSession, *, recent_limit: int = 20) -> GatewayHealth:
    """One row per registered route (task_type/priority/provider/model),
    each with its own kill-switch state and a recent-executions error
    rate - enough to answer "is this route actually healthy right now"
    without a raw SQL console.
    """
    models = (
        await session.execute(select(AIModel).order_by(AIModel.task_type, AIModel.priority))
    ).scalars().all()

    routes: list[RouteHealth] = []
    for model in models:
        provider = await session.get(AIProvider, model.provider_id)
        if provider is None:
            continue
        recent = (
            await session.execute(
                select(AIModelExecution)
                .where(AIModelExecution.model_id == model.id)
                .order_by(AIModelExecution.request_started_at.desc())
                .limit(recent_limit)
            )
        ).scalars().all()
        routes.append(
            RouteHealth(
                task_type=model.task_type, priority=model.priority,
                provider_code=provider.code, provider_status=provider.status,
                model_key=model.model_key, model_status=model.status,
                provider_killswitched=await _killswitch_active(
                    session, code=kill_switch_provider_code(provider.code)
                ),
                model_killswitched=await _killswitch_active(
                    session, code=kill_switch_model_code(model.id)
                ),
                recent_executions=len(recent),
                recent_errors=sum(1 for e in recent if e.error is not None),
            )
        )

    return GatewayHealth(
        global_killswitch_active=await _killswitch_active(
            session, code=KILL_SWITCH_GLOBAL_CODE
        ),
        routes=routes,
    )


async def activate_kill_switch(
    session: AsyncSession, *, code: str, reason: str, principal_id: uuid.UUID | None = None
) -> None:
    """Upserts by code (KillSwitch.code is unique) - reactivating an
    already-active switch just refreshes its reason/timestamp, same
    idempotent-by-construction pattern this codebase uses elsewhere.
    """
    switch = (
        await session.execute(select(KillSwitch).where(KillSwitch.code == code))
    ).scalar_one_or_none()
    now = dt.datetime.now(dt.UTC)
    if switch is None:
        session.add(
            KillSwitch(
                code=code, is_active=True, activated_at=now,
                activated_by_principal_id=principal_id, reason=reason,
            )
        )
    else:
        switch.is_active = True
        switch.activated_at = now
        switch.activated_by_principal_id = principal_id
        switch.reason = reason
    await session.commit()


async def deactivate_kill_switch(session: AsyncSession, *, code: str) -> bool:
    """False means no such switch exists at all - a real distinction from
    "existed and is now off", worth the caller knowing which happened.
    """
    switch = (
        await session.execute(select(KillSwitch).where(KillSwitch.code == code))
    ).scalar_one_or_none()
    if switch is None:
        return False
    switch.is_active = False
    await session.commit()
    return True
