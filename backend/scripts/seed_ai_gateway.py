"""Seeds the AI Gateway's provider/model registry (P4b AI-001 A0).

Run with:

    uv run python -m scripts.seed_ai_gateway

Idempotent: safe to run repeatedly, same pattern as scripts.seed_dev.

Talvrin's own model-tier decision: talvrin-go -> Groq, talvrin-pro ->
Gemini. Seeded honestly, not aspirationally - both providers are now
PRODUCTION, each proven live before promotion (same governance
discipline scripts.approve_calculation_spec.py applies to calc specs):

- gemini / gemini-flash-lite-latest for talvrin-pro. Only working
  Gemini model on the configured free-tier key - see
  ai_gateway/providers/gemini_client.py's docstring for the "pro" model
  line's zero-quota finding.
- groq / openai/gpt-oss-20b for talvrin-go, live-verified 2026-09-22
  once a GROQ_API_KEY existed - see
  ai_gateway/providers/groq_client.py's docstring. NOT
  llama-3.3-70b-versatile (this script's own earlier assumption) - that
  model doesn't exist on this key at all, found via a real
  GET /openai/v1/models call.

Idempotent re-runs also correct an existing model row's model_key/status
in place (keyed on provider+task_type, not provider+task_type+model_key)
so a prior wrong/unverified seed - like this script's own original
llama-3.3-70b-versatile row - gets fixed rather than left stale
alongside the corrected one.

A3 (routing, 2026-09-23) adds a real second route per task_type, not a
hypothetical one: each tier's non-primary provider is registered as its
priority-1 fallback (gateway.py's routing loop tries priority 0 first,
falls to priority 1 only if priority 0 is killswitched, keyless, or its
provider call errors). Both providers are already independently
live-verified PRODUCTION, so this is two real, working routes per tier,
not a stub with nothing to fail over to.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.ai_gateway.models import (
    STATUS_PRODUCTION,
    AIModel,
    AIProvider,
)

_TALVRIN_GO = "talvrin-go"
_TALVRIN_PRO = "talvrin-pro"


async def _seed_provider(
    session: AsyncSession, *, code: str, name: str, status: str
) -> AIProvider:
    provider = (
        await session.execute(select(AIProvider).where(AIProvider.code == code))
    ).scalar_one_or_none()
    if provider is None:
        provider = AIProvider(code=code, name=name, status=status)
        session.add(provider)
        await session.flush()
        print(f"  + ai_provider {code} -> {status}")
    elif provider.status != status:
        print(f"  ~ ai_provider {code} {provider.status} -> {status}")
        provider.status = status
    return provider


async def _seed_model(
    session: AsyncSession, *, provider: AIProvider, model_key: str, task_type: str, status: str,
    priority: int,
) -> None:
    existing = (
        await session.execute(
            select(AIModel).where(
                AIModel.provider_id == provider.id,
                AIModel.task_type == task_type,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            AIModel(
                provider_id=provider.id, model_key=model_key, task_type=task_type, status=status,
                priority=priority,
            )
        )
        print(
            f"  + ai_model {provider.code}/{model_key} for {task_type} "
            f"-> {status} (priority {priority})"
        )
    elif (existing.model_key, existing.status, existing.priority) != (model_key, status, priority):
        print(
            f"  ~ ai_model {provider.code} for {task_type}: "
            f"{existing.model_key}/{existing.status}/p{existing.priority} -> "
            f"{model_key}/{status}/p{priority}"
        )
        existing.model_key = model_key
        existing.status = status
        existing.priority = priority


async def seed() -> None:
    factory = get_session_factory()
    async with factory() as session:
        gemini = await _seed_provider(
            session, code="gemini", name="Google Gemini", status=STATUS_PRODUCTION
        )
        groq = await _seed_provider(
            session, code="groq", name="Groq", status=STATUS_PRODUCTION
        )

        # talvrin-pro: Gemini primary, Groq fallback.
        await _seed_model(
            session, provider=gemini, model_key="gemini-flash-lite-latest",
            task_type=_TALVRIN_PRO, status=STATUS_PRODUCTION, priority=0,
        )
        await _seed_model(
            session, provider=groq, model_key="openai/gpt-oss-20b",
            task_type=_TALVRIN_PRO, status=STATUS_PRODUCTION, priority=1,
        )

        # talvrin-go: Groq primary, Gemini fallback.
        await _seed_model(
            session, provider=groq, model_key="openai/gpt-oss-20b",
            task_type=_TALVRIN_GO, status=STATUS_PRODUCTION, priority=0,
        )
        await _seed_model(
            session, provider=gemini, model_key="gemini-flash-lite-latest",
            task_type=_TALVRIN_GO, status=STATUS_PRODUCTION, priority=1,
        )

        await session.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
