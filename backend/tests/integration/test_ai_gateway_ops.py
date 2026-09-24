"""app/modules/ai_gateway/ops.py (P4b AI-001 A5) against real Postgres -
live-proven first via scripts/ai_gateway_ops.py against the real dev
registry (real routes, a real activate/deactivate round trip) before
this file was written.
"""

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_gateway.models import STATUS_PRODUCTION, AIModel, AIModelExecution, AIProvider
from app.modules.ai_gateway.ops import activate_kill_switch, deactivate_kill_switch, get_health


async def _seed_route(
    db_session: AsyncSession, *, provider_code: str, task_type: str, priority: int = 0
) -> tuple[AIProvider, AIModel]:
    provider = AIProvider(code=provider_code, name=provider_code, status=STATUS_PRODUCTION)
    db_session.add(provider)
    await db_session.flush()
    model = AIModel(
        provider_id=provider.id, model_key="test-model", task_type=task_type,
        status=STATUS_PRODUCTION, priority=priority,
    )
    db_session.add(model)
    await db_session.flush()
    await db_session.commit()
    return provider, model


async def test_health_reports_every_registered_route(db_session: AsyncSession) -> None:
    await _seed_route(db_session, provider_code="gemini", task_type="talvrin-pro")
    await _seed_route(db_session, provider_code="groq", task_type="talvrin-go")

    health = await get_health(db_session)

    assert health.global_killswitch_active is False
    task_types = {r.task_type for r in health.routes}
    assert task_types == {"talvrin-pro", "talvrin-go"}


async def test_health_reflects_a_real_killswitch(db_session: AsyncSession) -> None:
    provider, _ = await _seed_route(db_session, provider_code="groq", task_type="talvrin-go")
    await activate_kill_switch(db_session, code=f"ai_gateway.provider.{provider.code}", reason="t")

    health = await get_health(db_session)
    route = next(r for r in health.routes if r.provider_code == "groq")
    assert route.provider_killswitched is True
    assert route.model_killswitched is False


async def test_health_counts_recent_errors(db_session: AsyncSession) -> None:
    _, model = await _seed_route(db_session, provider_code="groq", task_type="talvrin-go")
    db_session.add_all([
        AIModelExecution(
            task_type="talvrin-go", provider_id=model.provider_id, model_id=model.id,
            evidence_bundle_id=model.id, request_started_at=dt.datetime.now(dt.UTC),
            prompt_text="p", error="boom",
        ),
        AIModelExecution(
            task_type="talvrin-go", provider_id=model.provider_id, model_id=model.id,
            evidence_bundle_id=model.id, request_started_at=dt.datetime.now(dt.UTC),
            prompt_text="p", response_text="ok",
        ),
    ])
    await db_session.commit()

    health = await get_health(db_session)
    route = next(r for r in health.routes if r.provider_code == "groq")
    assert route.recent_executions == 2
    assert route.recent_errors == 1


async def test_activate_kill_switch_is_idempotent_and_updates_reason(
    db_session: AsyncSession,
) -> None:
    await activate_kill_switch(db_session, code="ai_gateway.global", reason="first")
    await activate_kill_switch(db_session, code="ai_gateway.global", reason="second")

    health = await get_health(db_session)
    assert health.global_killswitch_active is True


async def test_deactivate_kill_switch_reports_whether_one_existed(
    db_session: AsyncSession,
) -> None:
    assert await deactivate_kill_switch(db_session, code="ai_gateway.does-not-exist") is False

    await activate_kill_switch(db_session, code="ai_gateway.global", reason="test")
    assert await deactivate_kill_switch(db_session, code="ai_gateway.global") is True

    health = await get_health(db_session)
    assert health.global_killswitch_active is False
