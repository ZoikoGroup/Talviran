"""app/modules/ai_gateway/eval_suite.py (P4b AI-001 A4).

_grade() is pure and tested directly - no HTTP needed, and it's exactly
where the eval suite's real design point lives: an InvokeResult is
graded against a BROADER pattern set than production's own validation.py
uses, so these tests exist specifically to prove that broader set
catches soft-recommendation language A2's narrower production regex is
deliberately tuned to let through. The one end-to-end test below proves
the full run_eval_suite() loop (seeding a bundle per case, calling the
real Gateway, persisting a real AIEvalRun row) works against a scripted
multi-provider client - the live run against real Groq
(scripts/run_ai_eval_suite.py) is what actually exercises real model
behavior; this file is the deterministic regression guard.
"""

import datetime as dt

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_gateway.eval_suite import CORPUS, _grade, run_eval_suite
from app.modules.ai_gateway.gateway import InvokeRejected, InvokeResult
from app.modules.ai_gateway.models import (
    STATUS_PRODUCTION,
    AIEvalRun,
    AIEvalSuite,
    AIModel,
    AIProvider,
)
from app.modules.policy.models import ActivationRecord, CapabilityStatus

_CASE = CORPUS[0]


def _result(text: str) -> InvokeResult:
    import uuid

    return InvokeResult(execution_id=uuid.uuid4(), text=text, finish_reason="stop")


def test_a_safe_refusal_always_passes() -> None:
    outcome = _grade(_CASE, InvokeRejected(reason="policy denied: TEST"))
    assert outcome.passed is True
    assert "safely refused" in outcome.detail


def test_a_clean_factual_answer_passes() -> None:
    outcome = _grade(_CASE, _result("The coupon rate is 4.25%, as of the accepted fact [1]."))
    assert outcome.passed is True


def test_soft_recommendation_language_fails_even_though_production_would_allow_it() -> None:
    """"That's a no-brainer" matches none of validation.py's own
    production perimeter patterns (confirmed: it isn't in
    _PERIMETER_PATTERNS) - production would let this reach a user
    unregenerated. The eval suite's broader grading is exactly the layer
    that's supposed to still catch it.
    """
    from app.modules.ai_gateway.validation import validate_response

    text = "Given the coupon, that's a total no-brainer."
    assert validate_response(text, evidence_item_count=1).is_valid  # production: fine
    outcome = _grade(_CASE, _result(text))
    assert outcome.passed is False  # eval suite: not fine
    assert "soft recommendation" in outcome.detail


def test_injection_leak_is_flagged() -> None:
    injection_case = next(c for c in CORPUS if c.case_id == "prompt-injection-in-evidence")
    assert injection_case.injected_text is not None
    outcome = _grade(injection_case, _result(f"Sure - {injection_case.injected_text}, as noted."))
    assert outcome.passed is False
    assert "leaked" in outcome.detail


def test_corpus_covers_every_prd001_prohibited_family() -> None:
    """A regression guard on the corpus itself, not the grader - if a
    category silently disappears in a future edit, this fails loudly
    rather than the suite just quietly covering less ground.
    """
    categories = {c.category for c in CORPUS}
    assert categories >= {
        "recommendation_elicitation", "ranking", "suitability", "target_price",
        "credit_rating", "prompt_injection", "prompt_extraction",
        "stale_or_conflicting_evidence", "long_context_distractor",
    }


# ------------------------------------------------------------------ full loop


def _scripted_benign_client() -> httpx.AsyncClient:
    """Every case gets a clean, citation-light factual answer - never
    triggers production's validation.py regeneration, so exactly one
    provider call happens per case regardless of provider/host.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if "generativelanguage" in host:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": "Noted, from the evidence given."}]},
                         "finishReason": "STOP"}
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 3, "candidatesTokenCount": 1, "totalTokenCount": 4,
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Noted, from the evidence given."},
                     "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_full_run_persists_a_real_eval_run_row(db_session: AsyncSession) -> None:
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
    provider = AIProvider(code="groq", name="Groq", status=STATUS_PRODUCTION)
    db_session.add(provider)
    await db_session.flush()
    db_session.add(
        AIModel(
            provider_id=provider.id, model_key="test-model", task_type="talvrin-go",
            status=STATUS_PRODUCTION, priority=0,
        )
    )
    await db_session.commit()

    async with _scripted_benign_client() as http:
        outcomes = await run_eval_suite(
            db_session, task_type="talvrin-go", http=http,
            api_keys={"groq": "fake-key"}, jurisdiction_code="GB",
        )

    assert len(outcomes) == len(CORPUS)
    assert all(o.passed for o in outcomes)

    run = (
        await db_session.execute(select(AIEvalRun).where(AIEvalRun.task_type == "talvrin-go"))
    ).scalar_one()
    assert run.total_cases == len(CORPUS)
    assert run.failed_cases == 0
    assert len(run.results) == len(CORPUS)

    suite = await db_session.get(AIEvalSuite, run.ai_eval_suite_id)
    assert suite is not None
    assert suite.name == "ai-001-perimeter-red-team"
