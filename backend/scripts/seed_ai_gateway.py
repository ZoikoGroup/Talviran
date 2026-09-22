"""Seeds the AI Gateway's provider/model registry (P4b AI-001 A0).

Run with:

    uv run python -m scripts.seed_ai_gateway

Idempotent: safe to run repeatedly, same pattern as scripts.seed_dev.

Talvrin's own model-tier decision: talvrin-go -> Groq, talvrin-pro ->
Gemini. As of 2026-09-22, only Gemini's flash-lite-latest model is
actually verified working (see ai_gateway/providers/gemini_client.py's
docstring - the "pro" model line has zero free-tier quota on the
configured key). Seeded honestly, not aspirationally:

- gemini provider + a gemini-flash-lite-latest model registered for
  talvrin-pro, at PRODUCTION status - the one real, working end-to-end
  path this slice can actually prove.
- groq provider + its intended model registered for talvrin-go, but at
  CANDIDATE status - unverified, since no GROQ_API_KEY exists yet.
  Promote it to PRODUCTION only after it's actually been called
  successfully against a real key, same governance discipline
  scripts.approve_calculation_spec.py applies to calculation specs.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.ai_gateway.models import (
    STATUS_CANDIDATE,
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
    return provider


async def _seed_model(
    session: AsyncSession, *, provider: AIProvider, model_key: str, task_type: str, status: str
) -> None:
    existing = (
        await session.execute(
            select(AIModel).where(
                AIModel.provider_id == provider.id,
                AIModel.model_key == model_key,
                AIModel.task_type == task_type,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            AIModel(
                provider_id=provider.id, model_key=model_key, task_type=task_type, status=status
            )
        )
        print(f"  + ai_model {provider.code}/{model_key} for {task_type} -> {status}")


async def seed() -> None:
    factory = get_session_factory()
    async with factory() as session:
        gemini = await _seed_provider(
            session, code="gemini", name="Google Gemini", status=STATUS_PRODUCTION
        )
        await _seed_model(
            session, provider=gemini, model_key="gemini-flash-lite-latest",
            task_type=_TALVRIN_PRO, status=STATUS_PRODUCTION,
        )

        groq = await _seed_provider(
            session, code="groq", name="Groq", status=STATUS_CANDIDATE
        )
        await _seed_model(
            session, provider=groq, model_key="llama-3.3-70b-versatile",
            task_type=_TALVRIN_GO, status=STATUS_CANDIDATE,
        )

        await session.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
