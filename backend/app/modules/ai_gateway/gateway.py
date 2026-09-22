"""The single controlled path to a model provider (AI-001 §4.2's "No
bypass path": network egress policy must make direct provider calls
impossible from ordinary app modules; only Gateway workloads hold
provider credentials"). No other module may import
ai_gateway/providers/* directly - route every model call through
invoke_model().

A0 slice only (AI-001 §34's own staged sequence): resolves task_type ->
provider/model via the registry, checks kill switches, calls the
provider, records the forensic execution row (§18). Deliberately NOT
built yet, because the subsystems they depend on don't exist: PDP/rights
gating (needs A1's evidence path decision), the EvidenceBundle input
contract (A1), prompt templates and structured-output validation (A2),
multi-route provider failover (A3), and the full 14-step pipeline (§11)
this is the foundation of. Every caller of invoke_model right now is
therefore a script/test proving the foundation works, not the real
/research path - that wiring is a later slice's job, once grounding and
validation exist to make an ungrounded model reply safe to show a user.
"""

import datetime as dt
import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_gateway.models import (
    KILL_SWITCH_GLOBAL_CODE,
    STATUS_PRODUCTION,
    AIModel,
    AIModelExecution,
    AIProvider,
    kill_switch_model_code,
    kill_switch_provider_code,
)
from app.modules.ai_gateway.providers import gemini_client, groq_client
from app.modules.ai_gateway.providers.gemini_client import GeminiGenerationError
from app.modules.ai_gateway.providers.groq_client import GroqGenerationError
from app.modules.policy.models import KillSwitch


@dataclass(frozen=True)
class InvokeRejected:
    reason: str


@dataclass(frozen=True)
class InvokeResult:
    execution_id: uuid.UUID
    text: str
    finish_reason: str | None


async def _kill_switch_active(session: AsyncSession, *, code: str) -> bool:
    switch = (
        await session.execute(select(KillSwitch).where(KillSwitch.code == code))
    ).scalar_one_or_none()
    return switch is not None and switch.is_active


async def invoke_model(
    session: AsyncSession,
    *,
    task_type: str,
    prompt: str,
    http: httpx.AsyncClient,
    api_keys: dict[str, str],
) -> InvokeResult | InvokeRejected:
    """api_keys maps provider code -> API key (e.g. {"gemini": "...",
    "groq": "..."}) - the Gateway never reads Settings directly, so a
    test can supply fake keys without needing real config, and a future
    per-tenant/per-region key strategy doesn't require changing this
    function's shape.
    """
    if await _kill_switch_active(session, code=KILL_SWITCH_GLOBAL_CODE):
        return InvokeRejected(reason="AI Gateway global kill switch is active")

    model = (
        await session.execute(
            select(AIModel).where(
                AIModel.task_type == task_type, AIModel.status == STATUS_PRODUCTION
            )
        )
    ).scalar_one_or_none()
    if model is None:
        return InvokeRejected(
            reason=f"no PRODUCTION model registered for task_type {task_type!r}"
        )

    provider = await session.get(AIProvider, model.provider_id)
    if provider is None or provider.status != STATUS_PRODUCTION:
        return InvokeRejected(reason=f"provider for {task_type!r} is not PRODUCTION")

    if await _kill_switch_active(session, code=kill_switch_provider_code(provider.code)):
        return InvokeRejected(reason=f"kill switch active for provider {provider.code!r}")
    if await _kill_switch_active(session, code=kill_switch_model_code(model.id)):
        return InvokeRejected(reason=f"kill switch active for model {model.id}")

    api_key = api_keys.get(provider.code)
    if not api_key:
        return InvokeRejected(reason=f"no API key configured for provider {provider.code!r}")

    started_at = dt.datetime.now(dt.UTC)
    try:
        if provider.code == "gemini":
            result = await gemini_client.generate_content(
                http, model_key=model.model_key, prompt=prompt, api_key=api_key
            )
            text, finish_reason = result.text, result.finish_reason
            token_usage = {
                "prompt_tokens": result.prompt_token_count,
                "completion_tokens": result.candidates_token_count,
                "total_tokens": result.total_token_count,
            }
        elif provider.code == "groq":
            groq_result = await groq_client.generate_content(
                http, model_key=model.model_key, prompt=prompt, api_key=api_key
            )
            text, finish_reason = groq_result.text, groq_result.finish_reason
            token_usage = {
                "prompt_tokens": groq_result.prompt_tokens,
                "completion_tokens": groq_result.completion_tokens,
                "total_tokens": groq_result.total_tokens,
            }
        else:
            return InvokeRejected(reason=f"no adapter registered for provider {provider.code!r}")
    except (GeminiGenerationError, GroqGenerationError) as exc:
        session.add(
            AIModelExecution(
                task_type=task_type, provider_id=provider.id, model_id=model.id,
                request_started_at=started_at, response_received_at=dt.datetime.now(dt.UTC),
                prompt_text=prompt, error=str(exc)[:1000],
            )
        )
        await session.flush()
        return InvokeRejected(reason=f"provider call failed: {exc}")

    execution = AIModelExecution(
        task_type=task_type, provider_id=provider.id, model_id=model.id,
        request_started_at=started_at, response_received_at=dt.datetime.now(dt.UTC),
        prompt_text=prompt, response_text=text, finish_reason=finish_reason,
        token_usage=token_usage,
    )
    session.add(execution)
    await session.flush()

    return InvokeResult(execution_id=execution.id, text=text, finish_reason=finish_reason)
