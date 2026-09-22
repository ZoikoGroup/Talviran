"""app/modules/ai_gateway/gateway.py (P4b AI-001 A0) against real Postgres.

Provider calls use httpx.MockTransport (same pattern as conftest.py's
FakeSupabaseAuth and yesterday's Gemini embedding tests) - the real
Gemini API was already verified live before this was written (see
gateway.py's own docstring and scripts/seed_ai_gateway.py's real proof
run, 2026-09-22: a real invoke_model call against gemini-flash-lite-latest
returned a real "PONG" and wrote a real ai_model_execution row). The
automated suite doesn't depend on network/quota/cost for every run.
"""

import datetime as dt
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_gateway.gateway import InvokeRejected, InvokeResult, invoke_model
from app.modules.ai_gateway.models import (
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    AIModel,
    AIModelExecution,
    AIProvider,
)
from app.modules.policy.models import KillSwitch

_TASK_TYPE = "talvrin-pro"


async def _seed_provider_and_model(
    db_session: AsyncSession,
    *,
    provider_code: str = "gemini",
    provider_status: str = STATUS_PRODUCTION,
    model_status: str = STATUS_PRODUCTION,
    task_type: str = _TASK_TYPE,
) -> tuple[AIProvider, AIModel]:
    provider = AIProvider(code=provider_code, name=provider_code, status=provider_status)
    db_session.add(provider)
    await db_session.flush()
    model = AIModel(
        provider_id=provider.id, model_key="test-model", task_type=task_type,
        status=model_status,
    )
    db_session.add(model)
    await db_session.flush()
    await db_session.commit()
    return provider, model


def _fake_gemini_client(status_code: int = 200) -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        if status_code != 200:
            return httpx.Response(status_code, text="internal error")
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "PONG"}]}, "finishReason": "STOP"}
                ],
                "usageMetadata": {
                    "promptTokenCount": 3, "candidatesTokenCount": 1, "totalTokenCount": 4,
                },
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_successful_invocation_records_a_real_execution(
    db_session: AsyncSession,
) -> None:
    await _seed_provider_and_model(db_session)

    async with _fake_gemini_client() as http:
        result = await invoke_model(
            db_session, task_type=_TASK_TYPE, prompt="hi", http=http,
            api_keys={"gemini": "fake-key"},
        )
    await db_session.commit()

    assert isinstance(result, InvokeResult)
    assert result.text == "PONG"
    assert result.finish_reason == "STOP"

    execution = await db_session.get(AIModelExecution, result.execution_id)
    assert execution is not None
    assert execution.response_text == "PONG"
    assert execution.token_usage == {
        "prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4,
    }
    assert execution.error is None


async def test_no_production_model_for_task_type_is_rejected(
    db_session: AsyncSession,
) -> None:
    async with _fake_gemini_client() as http:
        result = await invoke_model(
            db_session, task_type="nonexistent-task", prompt="hi", http=http, api_keys={},
        )
    assert isinstance(result, InvokeRejected)


async def test_candidate_model_is_never_invoked(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session, model_status=STATUS_CANDIDATE)

    async with _fake_gemini_client() as http:
        result = await invoke_model(
            db_session, task_type=_TASK_TYPE, prompt="hi", http=http,
            api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)


async def test_candidate_provider_is_never_invoked_even_with_production_model(
    db_session: AsyncSession,
) -> None:
    await _seed_provider_and_model(db_session, provider_status=STATUS_CANDIDATE)

    async with _fake_gemini_client() as http:
        result = await invoke_model(
            db_session, task_type=_TASK_TYPE, prompt="hi", http=http,
            api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)


async def test_missing_api_key_is_rejected(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session)

    async with _fake_gemini_client() as http:
        result = await invoke_model(
            db_session, task_type=_TASK_TYPE, prompt="hi", http=http, api_keys={},
        )
    assert isinstance(result, InvokeRejected)
    assert "API key" in result.reason


async def test_unregistered_provider_code_is_rejected(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session, provider_code="unknown-vendor")

    async with _fake_gemini_client() as http:
        result = await invoke_model(
            db_session, task_type=_TASK_TYPE, prompt="hi", http=http,
            api_keys={"unknown-vendor": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)
    assert "no adapter" in result.reason


async def test_provider_error_is_recorded_not_raised(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session)

    async with _fake_gemini_client(status_code=500) as http:
        result = await invoke_model(
            db_session, task_type=_TASK_TYPE, prompt="hi", http=http,
            api_keys={"gemini": "fake-key"},
        )
    await db_session.commit()

    assert isinstance(result, InvokeRejected)
    execution = (
        await db_session.execute(
            select(AIModelExecution).where(AIModelExecution.task_type == _TASK_TYPE)
        )
    ).scalar_one()
    assert execution.error is not None
    assert execution.response_text is None


async def test_global_kill_switch_blocks_every_call(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session)
    db_session.add(
        KillSwitch(
            code="ai_gateway.global", is_active=True, activated_at=dt.datetime.now(dt.UTC),
            reason="test",
        )
    )
    await db_session.commit()

    async with _fake_gemini_client() as http:
        result = await invoke_model(
            db_session, task_type=_TASK_TYPE, prompt="hi", http=http,
            api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)
    assert "kill switch" in result.reason.lower()


async def test_provider_scoped_kill_switch_blocks_only_that_provider(
    db_session: AsyncSession,
) -> None:
    provider, _ = await _seed_provider_and_model(db_session)
    db_session.add(
        KillSwitch(
            code=f"ai_gateway.provider.{provider.code}", is_active=True,
            activated_at=dt.datetime.now(dt.UTC), reason="test",
        )
    )
    await db_session.commit()

    async with _fake_gemini_client() as http:
        result = await invoke_model(
            db_session, task_type=_TASK_TYPE, prompt="hi", http=http,
            api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)


async def test_model_scoped_kill_switch_blocks_only_that_model(
    db_session: AsyncSession,
) -> None:
    _, model = await _seed_provider_and_model(db_session)
    db_session.add(
        KillSwitch(
            code=f"ai_gateway.model.{model.id}", is_active=True,
            activated_at=dt.datetime.now(dt.UTC), reason="test",
        )
    )
    await db_session.commit()

    async with _fake_gemini_client() as http:
        result = await invoke_model(
            db_session, task_type=_TASK_TYPE, prompt="hi", http=http,
            api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)


async def test_inactive_kill_switch_does_not_block(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session)
    db_session.add(
        KillSwitch(code="ai_gateway.global", is_active=False, reason="test")
    )
    await db_session.commit()

    async with _fake_gemini_client() as http:
        result = await invoke_model(
            db_session, task_type=_TASK_TYPE, prompt="hi", http=http,
            api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeResult)


async def test_unrelated_kill_switch_code_does_not_block(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session)
    db_session.add(
        KillSwitch(
            code=f"ai_gateway.provider.{uuid.uuid4().hex}", is_active=True,
            activated_at=dt.datetime.now(dt.UTC), reason="test",
        )
    )
    await db_session.commit()

    async with _fake_gemini_client() as http:
        result = await invoke_model(
            db_session, task_type=_TASK_TYPE, prompt="hi", http=http,
            api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeResult)
