"""app/modules/ai_gateway/gateway.py (P4b AI-001 A0 + A1) against real
Postgres.

Provider calls use httpx.MockTransport (same pattern as conftest.py's
FakeSupabaseAuth and yesterday's Gemini embedding tests) - the real
Gemini and Groq APIs were already verified live before this was written
(see gateway.py's own docstring, providers/gemini_client.py and
providers/groq_client.py's proof runs). The automated suite doesn't
depend on network/quota/cost for every run.

A1 added two hard prerequisites every test now has to satisfy before a
call can even reach the provider: a PDP PERMIT (governance.capability_
status + governance.activation_record, same fixture pattern
test_evidence_research_answer.py uses) and a real, non-empty
EvidenceBundle. Tests that don't care about either just call the two
`_seed_*` helpers; tests that DO care (the new PDP/empty-bundle tests
below) deliberately skip one.
"""

import datetime as dt
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_gateway.gateway import InvokeRejected, InvokeResult, invoke_model
from app.modules.ai_gateway.models import (
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    AIModel,
    AIModelExecution,
    AIProvider,
)
from app.modules.evidence.models import EvidenceBundle, EvidenceMember
from app.modules.market.models import AcceptedFact
from app.modules.policy.allowed_output_type import AllowedOutputType
from app.modules.policy.models import ActivationRecord, CapabilityStatus, KillSwitch

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


async def _seed_capability_and_jurisdiction(db_session: AsyncSession) -> None:
    db_session.add(
        CapabilityStatus(
            capability_code="research.answer", jurisdiction_code=None, status="AVAILABLE"
        )
    )
    db_session.add(
        ActivationRecord(
            jurisdiction_code="GB", operating_entity="Test Entity", status="ACTIVE",
            effective_from=dt.datetime.now(dt.UTC) - dt.timedelta(days=1), effective_to=None,
        )
    )
    await db_session.commit()


async def _seed_evidence_bundle(db_session: AsyncSession) -> uuid.UUID:
    """A minimal but real bundle: one FACT member backed by a real
    AcceptedFact row - enough for evidence_path.render_grounded_prompt to
    produce a non-empty grounded prompt.
    """
    fact = AcceptedFact(
        subject_type="INSTRUMENT",
        subject_id=uuid.uuid4(),
        metric_id="TEST_METRIC",
        valid_range=Range(lower=dt.datetime(2026, 1, 1, tzinfo=dt.UTC), upper=None, bounds="[)"),
        knowledge_range=Range(
            lower=dt.datetime(2026, 1, 1, tzinfo=dt.UTC), upper=None, bounds="[)"
        ),
        value={"answer": "42"},
    )
    db_session.add(fact)
    await db_session.flush()

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    db_session.add(bundle)
    await db_session.flush()
    db_session.add(
        EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=fact.id)
    )
    await db_session.commit()
    return bundle.id


async def _empty_evidence_bundle(db_session: AsyncSession) -> uuid.UUID:
    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    db_session.add(bundle)
    await db_session.commit()
    return bundle.id


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


async def _invoke(
    db_session: AsyncSession,
    http: httpx.AsyncClient,
    *,
    task_type: str = _TASK_TYPE,
    evidence_bundle_id: uuid.UUID,
    api_keys: dict[str, str],
) -> InvokeResult | InvokeRejected:
    return await invoke_model(
        db_session,
        task_type=task_type,
        evidence_bundle_id=evidence_bundle_id,
        instruction="Answer the test question.",
        http=http,
        api_keys=api_keys,
        principal_id=None,
        account_id=None,
        jurisdiction_code="GB",
        requested_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
    )


async def test_successful_invocation_records_a_real_execution(
    db_session: AsyncSession,
) -> None:
    await _seed_provider_and_model(db_session)
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)

    async with _fake_gemini_client() as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id, api_keys={"gemini": "fake-key"},
        )
    await db_session.commit()

    assert isinstance(result, InvokeResult)
    assert result.text == "PONG"
    assert result.finish_reason == "STOP"

    execution = await db_session.get(AIModelExecution, result.execution_id)
    assert execution is not None
    assert execution.response_text == "PONG"
    assert execution.evidence_bundle_id == bundle_id
    assert "TEST_METRIC" in execution.prompt_text
    assert execution.token_usage == {
        "prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4,
    }
    assert execution.error is None


async def test_no_production_model_for_task_type_is_rejected(
    db_session: AsyncSession,
) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)

    async with _fake_gemini_client() as http:
        result = await _invoke(
            db_session, http, task_type="nonexistent-task", evidence_bundle_id=bundle_id,
            api_keys={},
        )
    assert isinstance(result, InvokeRejected)


async def test_candidate_model_is_never_invoked(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session, model_status=STATUS_CANDIDATE)
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)

    async with _fake_gemini_client() as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id, api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)


async def test_candidate_provider_is_never_invoked_even_with_production_model(
    db_session: AsyncSession,
) -> None:
    await _seed_provider_and_model(db_session, provider_status=STATUS_CANDIDATE)
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)

    async with _fake_gemini_client() as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id, api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)


async def test_missing_api_key_is_rejected(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session)
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)

    async with _fake_gemini_client() as http:
        result = await _invoke(db_session, http, evidence_bundle_id=bundle_id, api_keys={})
    assert isinstance(result, InvokeRejected)
    assert "API key" in result.reason


async def test_unregistered_provider_code_is_rejected(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session, provider_code="unknown-vendor")
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)

    async with _fake_gemini_client() as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id,
            api_keys={"unknown-vendor": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)
    assert "no adapter" in result.reason


async def test_provider_error_is_recorded_not_raised(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session)
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)

    async with _fake_gemini_client(status_code=500) as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id, api_keys={"gemini": "fake-key"},
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
    assert execution.evidence_bundle_id == bundle_id


async def test_global_kill_switch_blocks_every_call(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session)
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)
    db_session.add(
        KillSwitch(
            code="ai_gateway.global", is_active=True, activated_at=dt.datetime.now(dt.UTC),
            reason="test",
        )
    )
    await db_session.commit()

    async with _fake_gemini_client() as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id, api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)
    assert "kill switch" in result.reason.lower()


async def test_provider_scoped_kill_switch_blocks_only_that_provider(
    db_session: AsyncSession,
) -> None:
    provider, _ = await _seed_provider_and_model(db_session)
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)
    db_session.add(
        KillSwitch(
            code=f"ai_gateway.provider.{provider.code}", is_active=True,
            activated_at=dt.datetime.now(dt.UTC), reason="test",
        )
    )
    await db_session.commit()

    async with _fake_gemini_client() as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id, api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)


async def test_model_scoped_kill_switch_blocks_only_that_model(
    db_session: AsyncSession,
) -> None:
    _, model = await _seed_provider_and_model(db_session)
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)
    db_session.add(
        KillSwitch(
            code=f"ai_gateway.model.{model.id}", is_active=True,
            activated_at=dt.datetime.now(dt.UTC), reason="test",
        )
    )
    await db_session.commit()

    async with _fake_gemini_client() as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id, api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)


async def test_inactive_kill_switch_does_not_block(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session)
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)
    db_session.add(
        KillSwitch(code="ai_gateway.global", is_active=False, reason="test")
    )
    await db_session.commit()

    async with _fake_gemini_client() as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id, api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeResult)


async def test_unrelated_kill_switch_code_does_not_block(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session)
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)
    db_session.add(
        KillSwitch(
            code=f"ai_gateway.provider.{uuid.uuid4().hex}", is_active=True,
            activated_at=dt.datetime.now(dt.UTC), reason="test",
        )
    )
    await db_session.commit()

    async with _fake_gemini_client() as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id, api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeResult)


# ------------------------------------------------------------------ A1: PDP gate


async def test_pdp_deny_blocks_the_call_before_any_provider_request(
    db_session: AsyncSession,
) -> None:
    """No _seed_capability_and_jurisdiction call - an unregistered
    capability is DENY by the PDP's own fail-closed default (POL-001),
    exactly like every other protected capability in this codebase.
    """
    await _seed_provider_and_model(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("provider must never be called when the PDP denies")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id, api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)
    assert "policy denied" in result.reason


async def test_jurisdiction_not_activated_is_denied(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session)
    bundle_id = await _seed_evidence_bundle(db_session)
    db_session.add(
        CapabilityStatus(
            capability_code="research.answer", jurisdiction_code=None, status="AVAILABLE"
        )
    )
    await db_session.commit()  # deliberately no ActivationRecord for GB

    async with _fake_gemini_client() as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id, api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)
    assert "policy denied" in result.reason


# ------------------------------------------------------------------ A1: evidence bundle contract


async def test_empty_evidence_bundle_is_rejected_not_generated_ungrounded(
    db_session: AsyncSession,
) -> None:
    await _seed_provider_and_model(db_session)
    await _seed_capability_and_jurisdiction(db_session)
    bundle_id = await _empty_evidence_bundle(db_session)

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("provider must never be called with no grounding evidence")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=bundle_id, api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)
    assert "empty" in result.reason or "missing" in result.reason


async def test_nonexistent_evidence_bundle_is_rejected(db_session: AsyncSession) -> None:
    await _seed_provider_and_model(db_session)
    await _seed_capability_and_jurisdiction(db_session)

    async with _fake_gemini_client() as http:
        result = await _invoke(
            db_session, http, evidence_bundle_id=uuid.uuid4(), api_keys={"gemini": "fake-key"},
        )
    assert isinstance(result, InvokeRejected)
