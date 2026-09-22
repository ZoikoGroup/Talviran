"""The single controlled path to a model provider (AI-001 §4.2's "No
bypass path": network egress policy must make direct provider calls
impossible from ordinary app modules; only Gateway workloads hold
provider credentials"). No other module may import
ai_gateway/providers/* directly - route every model call through
invoke_model().

A0 (foundation) + A1 (evidence path) + A2 (validation) now, per AI-001
§34's own staged sequence: resolves task_type -> provider/model via the
registry, checks kill switches, runs the request through the same PDP
every other protected capability uses (app.modules.policy.pdp - fixed
precedence, fail-closed), refuses to call a provider at all unless a
real, non-empty EvidenceBundle backs the prompt
(app.modules.ai_gateway.evidence_path - AI-001 §23, "empty evidence
bundle -> never generate a speculative answer"), calls the provider,
validates the response (app.modules.ai_gateway.validation - citation
indices must exist in the bundle given, no recommendation-shaped
language), and on a validation failure makes exactly one bounded
regeneration attempt before giving up (AI-001 §23: "invalid schema/
grounding/citation failure -> one regeneration then evidence-only" - a
caller that gets InvokeRejected back after a validation failure is
expected to fall back to an evidence-only render, never retry itself).
Every attempt's forensic execution row (§18) records the
evidence_bundle_id that grounded it; every validated response gets its
own ai_validation_result row.

Deliberately NOT built yet: multi-route provider failover (A3) and the
rest of the full 14-step pipeline (§11) this is the foundation of. Every
caller of invoke_model right now is therefore a script/test proving the
evidence+validation path works, not the real /research path - swapping
/research's rule-based text assembly for Gateway-composed prose is still
a later slice's job.
"""

import datetime as dt
import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_gateway.evidence_path import render_grounded_prompt
from app.modules.ai_gateway.models import (
    KILL_SWITCH_GLOBAL_CODE,
    STATUS_PRODUCTION,
    AIModel,
    AIModelExecution,
    AIProvider,
    AIValidationResult,
    kill_switch_model_code,
    kill_switch_provider_code,
)
from app.modules.ai_gateway.providers import gemini_client, groq_client
from app.modules.ai_gateway.providers.gemini_client import GeminiGenerationError
from app.modules.ai_gateway.providers.groq_client import GroqGenerationError
from app.modules.ai_gateway.validation import validate_response
from app.modules.evidence.service import RESEARCH_CAPABILITY_CODE
from app.modules.policy.allowed_output_type import AllowedOutputType
from app.modules.policy.models import KillSwitch
from app.modules.policy.pdp import PolicyContext
from app.modules.policy.pdp import evaluate as pdp_evaluate


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
    evidence_bundle_id: uuid.UUID,
    instruction: str,
    http: httpx.AsyncClient,
    api_keys: dict[str, str],
    principal_id: uuid.UUID | None,
    account_id: uuid.UUID | None,
    jurisdiction_code: str | None,
    requested_output_type: AllowedOutputType,
) -> InvokeResult | InvokeRejected:
    """api_keys maps provider code -> API key (e.g. {"gemini": "...",
    "groq": "..."}) - the Gateway never reads Settings directly, so a
    test can supply fake keys without needing real config, and a future
    per-tenant/per-region key strategy doesn't require changing this
    function's shape.

    No bare `prompt: str` anymore (A1): callers hand over an
    evidence_bundle_id (already assembled by evidence.service - this
    module does no retrieval of its own) plus the task instruction, and
    this function renders the grounded prompt itself so a caller can
    never accidentally slip in ungrounded text. principal_id/account_id/
    jurisdiction_code/requested_output_type feed the same PDP every other
    protected capability goes through - reuses RESEARCH_CAPABILITY_CODE
    because an AI-composed research answer and a rule-based one are the
    same governed product capability, just a different execution path.
    """
    if await _kill_switch_active(session, code=KILL_SWITCH_GLOBAL_CODE):
        return InvokeRejected(reason="AI Gateway global kill switch is active")

    policy_decision = await pdp_evaluate(
        session,
        PolicyContext(
            principal_id=principal_id,
            account_id=account_id,
            jurisdiction_code=jurisdiction_code,
            capability_code=RESEARCH_CAPABILITY_CODE,
            requested_output_type=requested_output_type,
        ),
    )
    if not policy_decision.is_permit:
        return InvokeRejected(
            reason=f"policy denied: {', '.join(policy_decision.reason_codes)}"
        )

    grounded = await render_grounded_prompt(
        session, bundle_id=evidence_bundle_id, instruction=instruction
    )
    if grounded is None:
        return InvokeRejected(
            reason=(
                f"evidence bundle {evidence_bundle_id} is missing or has no "
                "renderable items - refusing to generate an ungrounded reply"
            )
        )
    prompt = grounded.text

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

    async def _call_provider(
        call_prompt: str,
    ) -> tuple[InvokeResult, AIModelExecution] | InvokeRejected:
        started_at = dt.datetime.now(dt.UTC)
        try:
            if provider.code == "gemini":
                result = await gemini_client.generate_content(
                    http, model_key=model.model_key, prompt=call_prompt, api_key=api_key
                )
                text, finish_reason = result.text, result.finish_reason
                token_usage = {
                    "prompt_tokens": result.prompt_token_count,
                    "completion_tokens": result.candidates_token_count,
                    "total_tokens": result.total_token_count,
                }
            elif provider.code == "groq":
                groq_result = await groq_client.generate_content(
                    http, model_key=model.model_key, prompt=call_prompt, api_key=api_key
                )
                text, finish_reason = groq_result.text, groq_result.finish_reason
                token_usage = {
                    "prompt_tokens": groq_result.prompt_tokens,
                    "completion_tokens": groq_result.completion_tokens,
                    "total_tokens": groq_result.total_tokens,
                }
            else:
                return InvokeRejected(
                    reason=f"no adapter registered for provider {provider.code!r}"
                )
        except (GeminiGenerationError, GroqGenerationError) as exc:
            session.add(
                AIModelExecution(
                    task_type=task_type, provider_id=provider.id, model_id=model.id,
                    evidence_bundle_id=evidence_bundle_id,
                    request_started_at=started_at,
                    response_received_at=dt.datetime.now(dt.UTC),
                    prompt_text=call_prompt, error=str(exc)[:1000],
                )
            )
            await session.flush()
            return InvokeRejected(reason=f"provider call failed: {exc}")

        execution = AIModelExecution(
            task_type=task_type, provider_id=provider.id, model_id=model.id,
            evidence_bundle_id=evidence_bundle_id,
            request_started_at=started_at, response_received_at=dt.datetime.now(dt.UTC),
            prompt_text=call_prompt, response_text=text, finish_reason=finish_reason,
            token_usage=token_usage,
        )
        session.add(execution)
        await session.flush()
        invoke_result = InvokeResult(
            execution_id=execution.id, text=text, finish_reason=finish_reason
        )
        return invoke_result, execution

    outcome = await _call_provider(prompt)
    if isinstance(outcome, InvokeRejected):
        return outcome  # transport/provider failure - nothing to validate

    result, execution = outcome
    validation = validate_response(result.text, evidence_item_count=grounded.evidence_item_count)
    session.add(
        AIValidationResult(
            ai_model_execution_id=execution.id, passed=validation.is_valid,
            failure_reasons=validation.failure_reasons or None,
        )
    )
    await session.flush()
    if validation.is_valid:
        return result

    # AI-001 §23: exactly one bounded regeneration on validation failure.
    regen_prompt = (
        f"{prompt}\n\nYour previous answer failed validation for this reason: "
        f"{'; '.join(validation.failure_reasons)}. Answer again, correcting this - "
        "do not repeat the same mistake."
    )
    regen_outcome = await _call_provider(regen_prompt)
    if isinstance(regen_outcome, InvokeRejected):
        return regen_outcome

    regen_result, regen_execution = regen_outcome
    regen_validation = validate_response(
        regen_result.text, evidence_item_count=grounded.evidence_item_count
    )
    session.add(
        AIValidationResult(
            ai_model_execution_id=regen_execution.id, passed=regen_validation.is_valid,
            failure_reasons=regen_validation.failure_reasons or None,
        )
    )
    await session.flush()
    if regen_validation.is_valid:
        return regen_result

    return InvokeRejected(
        reason=(
            "response failed validation twice (regeneration exhausted) - caller "
            f"must fall back to an evidence-only render: "
            f"{'; '.join(regen_validation.failure_reasons)}"
        )
    )
