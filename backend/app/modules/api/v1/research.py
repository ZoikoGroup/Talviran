"""POST /api/v1/research (P1 week 13, API-001 shape) — the endpoint the
frontend's chat UI actually calls per turn. Stores the caller's message and
the generated reply through research.service.append_message, using both
roles exactly the way that module's own MessageIn docstring anticipated
("Assistant and system turns are written by the server, through the
service layer") — no changes to the research/chats schema or its other
endpoints, this is purely an additional caller of its existing public API.

Idempotency-Key is required (API-001, core/idempotency.py — built in week 6,
wired into a real endpoint for the first time here): a retried request with
the same key and body replays the stored response rather than appending the
turn twice; the same key with a different body is a 409, never a silent
overwrite.

The idempotency cache key is scoped by account_id (2026-11-15 UAT gap
analysis G10 remediation): core/idempotency.py's own docstring flagged this
as a known gap when it was first built ("scope should be widened to include
principal_id once real auth exists") and real auth has existed since P2, but
the call site here was never updated. Without this, the Redis record is
keyed only on the client-supplied Idempotency-Key header + a hash of the
raw request body — nothing about the authenticated caller — so a second
tenant who ever replayed the exact same header value against the exact same
request bytes (e.g. a leaked/guessed key, a shared proxy cache, a replayed
request) would get back the FIRST tenant's stored research answer straight
from Redis, with no RLS or PDP check in that path at all: `run_idempotent`
returns the cached body before `_handler` (where every permission check
lives) ever runs. Folding account_id into `scope` makes that collision
structurally impossible — two tenants now write into disjoint key spaces no
matter what Idempotency-Key value or body either of them chooses.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ErrorCode, TalvrinAPIError
from app.core.idempotency import IdempotencyConflictError, run_idempotent
from app.core.request_context import get_request_id
from app.modules.ai_gateway.gateway import InvokeResult, invoke_model
from app.modules.api.v1.auth import HttpDep
from app.modules.api.v1.deps import DekDep, IdentityDep, RedisDep, SessionDep
from app.modules.evidence import service as evidence_service
from app.modules.evidence.models import EvidenceBundle
from app.modules.evidence.service import DEV_JURISDICTION
from app.modules.research import service as research_service

router = APIRouter(tags=["research"])

logger = logging.getLogger(__name__)

_IDEMPOTENCY_SCOPE = "POST /api/v1/research"


class ResearchIn(BaseModel):
    conversation_id: uuid.UUID
    query: str = Field(min_length=1, max_length=research_service.MAX_MESSAGE_LENGTH)
    model: str | None = None


class CitationOut(BaseModel):
    label: str
    meta: str | None
    pill: str
    kind: str
    url: str | None = None


class FactTableOut(BaseModel):
    title: str
    rows: list[tuple[str, str]]


class ResearchOut(BaseModel):
    request_id: str
    generated_at: dt.datetime
    evidence_bundle_id: uuid.UUID | None
    allowed_output_type: str
    message_id: uuid.UUID
    text: str
    facts: FactTableOut | None
    citations: list[CitationOut]
    note: str | None


class EvidenceItemOut(BaseModel):
    kind: str
    subject_type: str | None
    metric_id: str | None
    value: dict[str, Any] | None
    basis: str | None
    as_of: str | None
    effective_time: str | None
    source: str | None
    permitted_use: str | None
    document_title: str | None
    text: str | None


class EvidenceOut(BaseModel):
    evidence_bundle_id: uuid.UUID | None
    purpose_type: str | None
    status: str | None
    items: list[EvidenceItemOut]


def _not_found() -> TalvrinAPIError:
    return TalvrinAPIError(code=ErrorCode.NOT_FOUND, message="Not found.")


def _too_long(exc: research_service.ContentTooLong) -> TalvrinAPIError:
    return TalvrinAPIError(code=ErrorCode.VALIDATION_ERROR, message=str(exc))


#: AI-001's "the platform must keep answering correctly with the Gateway
#: turned off" invariant, extended from *presence* to *quality*: AI
#: composition may enrich the rule-based answer but must never negate it.
#:
#: Found live 2026-10-15 (finding F10): `_ACCRUED_EXPLANATION_TEXT` says
#: "For gilts the accrual uses ACT/ACT (ICMA)" and the seeded accepted
#: fact for GB0032452392 says `Day count = ACT/ACT (ICMA)`, yet `what day
#: count convention do gilts use?` and `what is ACT/ACT?` both came back
#: as "the evidence does not state / define this" - a correct
#: deterministic answer replaced by a denial of the platform's own
#: knowledge. The same mechanism was already visible in F4, where the
#: curated accrued-interest definition came back as "cannot be derived".
#:
#: Detected structurally rather than with a second LLM call: a model that
#: declines to answer at all is always worse than the rule-based answer
#: it would replace, so this needs no judgement about which prose is
#: *better*. Tuned against all 55 live responses of the 2026-10-15 run -
#: every one of the 6 genuine declinations caught, none of the 49
#: substantive answers misclassified.
#:
#: Applies to every branch, including the document fallback (whose `text`
#: is a raw source excerpt, not prose we authored). An early draft exempted
#: it on the grounds that an excerpt is evidence rather than an answer - a
#: re-run on 2026-10-15 falsified that: "what is a primary dealer?" came
#: back as "the evidence does not contain enough information to define or
#: describe what a primary dealer is", and the excerpt this guard would
#: have kept is page 8 of the GEMM Guidebook, which defines exactly that.
#: A denial of a corpus that does contain the answer is never the better
#: response, however the text was produced.
_AI_DECLINATION_PATTERN = re.compile(
    r"\b(?:cannot|can't|could not|unable to)\s+"
    r"(?:answer|determine|derive|provide|confirm|be determined)\b"
    r"|\b(?:does not|doesn't|do not|don't|did not|cannot|can't)\s+"
    r"(?:contain|includes?|include|provide|state|define|identify|list|show"
    r"|cover|mention|record|address)\b[^.?!]{0,80}"
    r"\b(?:evidence|document|material|data|tables?|sources?)\b"
    r"|\b(?:evidence|document|material|data|tables?|sources?)\b[^.?!]{0,80}"
    r"\b(?:does not|doesn't|do not|don't|did not|cannot|can't|is not"
    r"|are not|was not)\s+"
    r"(?:contain|includes?|include|provide|state|define|identify|list|show"
    r"|cover|mention|record|address)\b"
    r"|\b(?:insufficient|no|not enough)\s+evidence\b"
    r"|\bdo(?:es)? not have\b[^.?!]{0,60}\bevidence\b"
    r"|\bno information\s+(?:about|on|regarding)\b",
    re.I,
)


#: The one FX fact-table row labels this guard reads (see
#: evidence_service._fx_rate_reply, which authors them) - "GBP/USD" is the
#: pair's NAME (conventionally read quote-per-base) and is deliberately
#: NOT treated as a unit assertion below; only an explicit "N <currency>
#: per <currency>" phrase asserts one.
_FX_PAIR_ROW_LABEL = "Currency pair"
_FX_RATE_ROW_LABEL = "Spot rate"
_FX_UNIT_PHRASE_PATTERN = re.compile(
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<c1>GBP|USD|pounds?|dollars?|sterling)\s*"
    r"(?:per|a|for each|for one)\s+"
    r"(?P<c2>GBP|USD|pounds?|dollars?|sterling)",
    re.I,
)
_FX_CURRENCY_CODES = {
    "gbp": "GBP",
    "pound": "GBP",
    "pounds": "GBP",
    "sterling": "GBP",
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
}
#: Relative slack for the comparison below. Generous enough for prose
#: rounding ("1.33 USD per GBP", or a reciprocal "0.75 GBP per USD" both
#: pass), yet far below any real inversion: the F5 bug said the same
#: figure was "GBP per USD" instead of "USD per GBP" - ~76% off the value
#: that direction implies, so a 5% bar separates the two classes cleanly.
_FX_UNIT_TOLERANCE = Decimal("0.05")


def _fx_unit_contradicts(
    facts: evidence_service.FactTable | None, text: str
) -> bool:
    """F5 guard (found live 2026-10-15): AI-composed prose inverted the
    FX rate's unit - the deterministic answer's facts table says the rate
    is quote-per-base (1.3266 USD per GBP) while the composed sentence
    labelled the very same figure "GBP per USD", a materially wrong
    statement about which currency was worth what. _AI_DECLINATION_PATTERN
    only catches a model that refuses to answer; this catches a model
    that answers confidently with the units flipped.

    Deterministic, no second LLM call, same doctrine as that guard: when
    composed prose contradicts the accepted facts it is built on, the
    prose goes and the rule-based answer stays. Only phrases naming both
    sides of the canonical pair are judged - anything else is left
    entirely to the composition, exactly as before.
    """
    if facts is None:
        return False
    rows = dict(facts.rows)
    pair, rate_text = rows.get(_FX_PAIR_ROW_LABEL), rows.get(_FX_RATE_ROW_LABEL)
    if pair is None or rate_text is None or "/" not in pair:
        return False  # not an FX answer (or an unexpected shape) - nothing to check
    base, quote = (side.strip().upper() for side in pair.split("/", 1))
    try:
        rate = Decimal(rate_text)
    except InvalidOperation:
        return False
    if rate <= 0:
        return False

    for match in _FX_UNIT_PHRASE_PATTERN.finditer(text):
        first = _FX_CURRENCY_CODES[match["c1"].lower()]
        second = _FX_CURRENCY_CODES[match["c2"].lower()]
        if first == second or {first, second} != {base, quote}:
            continue  # not this pair's two currencies - nothing to judge
        try:
            value = Decimal(match["value"].replace(",", ""))
        except InvalidOperation:
            continue
        if value <= 0:
            continue
        # The facts' rate is quote-per-base: "N <quote> per <base>" is the
        # canonical direction and must carry the rate itself; the inverted
        # direction must carry its reciprocal.
        expected = rate if first == quote else Decimal(1) / rate
        if abs(value - expected) > expected * _FX_UNIT_TOLERANCE:
            return True
    return False


#: 2026-11-02, 205-query battery: the same "composed prose contradicted the
#: accepted facts" defect class as F5, now for three deterministic claims the
#: platform already knows exactly:
#:   - day count: the fact and curated text say ACT/ACT (ICMA), but a composed
#:     answer said 30/360 (line 15, reproduced across five runs);
#:   - ex-dividend: the DMO rule is seven business days before the coupon, but
#:     a composed answer said "the day before settlement" (line 14);
#:   - inventory completeness: the platform holds 70 gilts with reference
#:     terms, but composed answers claimed "a single UK gilt" on list questions
#:     (lines 76-80, 144-145).
#: None of these needs a second LLM call: each has a canonical token/phrase in
#: the deterministic answer and a known contradiction pattern, so a model that
#: departs from it is rejected exactly like a declination.
_DAY_COUNT_QUERY_PATTERN = re.compile(
    r"day[- ]?count|daycount|act/act|actual/actual", re.I
)
_DAY_COUNT_CANONICAL_PATTERN = re.compile(
    r"ACT/ACT\s*\(ICMA\)|ACTUAL/ACTUAL\s*\(ICMA\)", re.I
)
_DAY_COUNT_CONTRADICTION_PATTERN = re.compile(
    r"30/360|actual/360|30/actual", re.I
)
_EX_DIVIDEND_QUERY_PATTERN = re.compile(r"ex[- ]?div(?:idend)?|\bxd\b", re.I)
_EX_DIVIDEND_CANONICAL_PATTERN = re.compile(
    r"(?:seven|7)\s+business\s+days", re.I
)
_EX_DIVIDEND_CONTRADICTION_PATTERN = re.compile(
    r"day\s+(?:before|prior\s+to)\s+(?:the\s+)?(?:settlement|coupon|dividend)"
    r"|one\s+day\s+before",
    re.I,
)
_SINGLE_GILT_CLAIM_PATTERN = re.compile(
    r"\b(?:only|single)\s+(?:onboarded\s+|available\s+|UK\s+)?"
    r"(?:gilt|instrument|bond|Treasury\s+(?:Stock|Gilt))\b"
    r"|\bno additional gilts?\b"
    r"|\bthe current onboarded gilt\b"
    r"|\b(?:only|single)\s+(?:\d[\d.\u00bc\u00bd\u00be/ ]*%\s+)?Treasury\s+(?:Stock|Gilt)\b",
    re.I,
)
_MULTIPLE_INSTRUMENT_CLAIM_PATTERN = re.compile(
    r"\b(?:two|three|four|multiple|several)\s+(?:distinct\s+)?"
    r"(?:gilt|bond|treasury|instrument)s?\b",
    re.I,
)
_RANKING_SUPERLATIVE_PATTERN = re.compile(
    r"\b(?:highest|lowest|best|worst|most attractive|top[- ]yielding|top performer)\b",
    re.I,
)
_COMPARISON_QUERY_PATTERN = re.compile(
    r"\b(?:compare|comparison|vs\.?|versus|spread|difference)\b", re.I
)


def _convention_contradicts(query_text: str, text: str) -> bool:
    """True when composed `text` contradicts a deterministic convention
    answer for `query_text`. Checked only for queries that actually ask
    about the convention, so unrelated answers are untouched.
    """
    if _DAY_COUNT_QUERY_PATTERN.search(query_text):
        if _DAY_COUNT_CONTRADICTION_PATTERN.search(text) or not (
            _DAY_COUNT_CANONICAL_PATTERN.search(text)
        ):
            return True
    if _EX_DIVIDEND_QUERY_PATTERN.search(query_text):
        if _EX_DIVIDEND_CONTRADICTION_PATTERN.search(text) or not (
            _EX_DIVIDEND_CANONICAL_PATTERN.search(text)
        ):
            return True
    return False


def _completeness_contradicts(text: str) -> bool:
    """True when composed prose claims the platform holds only one gilt (or
    no additional gilts). The platform's reference data holds 70, so this is
    a factual completeness claim that is never acceptable regardless of the
    question that prompted it.
    """
    return bool(_SINGLE_GILT_CLAIM_PATTERN.search(text))


def _instrument_count_contradicts(
    facts: evidence_service.FactTable | None, text: str
) -> bool:
    """True when a single-instrument answer's composed prose claims multiple
    instruments. The facts table is the deterministic record of how many
    instruments the answer covers; a model that turns one into "two gilt
    instruments" is inventing a second instrument (observed live on the
    2026 maturity question, 2026-11-02 re-run).
    """
    if facts is None or facts.title != "Instrument facts":
        return False
    return bool(_MULTIPLE_INSTRUMENT_CLAIM_PATTERN.search(text))


def _ranking_superlative_leaks(query_text: str, text: str) -> bool:
    """True when composed prose introduces a best/highest/top-yielding
    ranking the user did not ask for. Comparison questions are exempt:
    "compare the 2032 and 2036 gilts" legitimately needs comparative prose.
    """
    if _COMPARISON_QUERY_PATTERN.search(query_text):
        return False
    if not _RANKING_SUPERLATIVE_PATTERN.search(text):
        return False
    return bool(
        re.search(
            r"\b(?:gilt|bond|treasury|instrument|dataset|listed|onboarded)\b",
            text,
            re.I,
        )
    )


async def _try_ai_composed_text(
    db: AsyncSession,
    *,
    answer: evidence_service.ResearchAnswer,
    query_text: str,
    conversation_id: uuid.UUID,
    principal_id: uuid.UUID,
    account_id: uuid.UUID,
    dek: bytes,
    http: httpx.AsyncClient,
    model: str | None = None,
) -> evidence_service.ResearchAnswer:
    """Best-effort AI Gateway composition on top of the rule-based answer
    evidence_service already produced - AI-001 A0+A1+A2 wired into the
    real product path for the first time. Only attempted when a real
    EvidenceBundle exists (an advice-redirect/greeting/no-data reply has
    nothing for the model to explain - A1's own empty-bundle rule would
    reject it anyway, this just skips the wasted call). Any rejection
    (no PRODUCTION model, PDP deny, validation failed twice, provider
    down) silently keeps the original rule-based text - "AI is fully
    removable" is a real product invariant, not aspirational: the
    platform must keep answering correctly with the Gateway turned off.
    A model that returns a declination instead of an answer is treated
    the same way (see _AI_DECLINATION_PATTERN).
    """
    if answer.evidence_bundle_id is None:
        return answer

    if answer.facts is not None and answer.facts.title.startswith("Onboarded UK gilts"):
        # Inventory answers are already a complete, deterministic list; a
        # model summarising a 70-row table can drop rows or state a wrong
        # count (the 205-query battery's 2040s answer claimed "two distinct
        # issues" for a 13-row decade). Keep the rule-based inventory text
        # and its full facts table unchanged.
        return answer

    if answer.note is not None and answer.note.startswith("Deterministic convention answer"):
        # Day-count and ex-dividend answers are correctness-critical and
        # have already been contradicted by composition (30/360, "day
        # before settlement"). Keep the deterministic prose while still
        # carrying the DMO EvidenceBundle/Citation attached above.
        return answer

    conversation = await research_service.get_conversation(
        db, conversation_id=conversation_id, dek=dek
    )
    task_type = model or conversation.model
    if model and model != conversation.model:
        await research_service.set_conversation_model(
            db, conversation_id=conversation_id, model=model
        )
    settings = get_settings()
    api_keys = {
        code: key
        for code, key in {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key}.items()
        if key
    }

    try:
        outcome = await invoke_model(
            db,
            task_type=task_type,
            evidence_bundle_id=answer.evidence_bundle_id,
            instruction=query_text,
            http=http,
            api_keys=api_keys,
            principal_id=principal_id,
            account_id=account_id,
            jurisdiction_code=DEV_JURISDICTION,
            requested_output_type=answer.allowed_output_type,
        )
    except Exception:
        # invoke_model already turns every anticipated failure (kill
        # switch, PDP deny, no PRODUCTION model, a provider's own
        # Generation/transport errors) into InvokeRejected - this is only
        # reached by something genuinely unanticipated (e.g. a malformed
        # provider response shape). "AI is fully removable" means this
        # must still degrade to the rule-based answer already computed
        # above, never a raw internal error - the real exception is
        # logged here for diagnosis, not silently discarded.
        logger.exception("AI Gateway invoke_model failed unexpectedly for %r", task_type)
        return answer
    if isinstance(outcome, InvokeResult):
        if _AI_DECLINATION_PATTERN.search(outcome.text):
            # The model declined to answer rather than composed one. Keep
            # the rule-based text (facts/citations/bundle are untouched
            # either way) instead of downgrading a working answer into a
            # denial of what the platform holds - see
            # _AI_DECLINATION_PATTERN.
            return answer
        if _fx_unit_contradicts(answer.facts, outcome.text):
            # Same reasoning, different defect class (F5): composed prose
            # that states the FX rate with its unit inverted contradicts
            # the accepted fact it was built on - keep the rule-based
            # answer rather than publishing a materially wrong sentence
            # next to a correct facts table.
            return answer
        if _convention_contradicts(query_text, outcome.text):
            # Day-count / ex-dividend composition contradicted the
            # deterministic convention answer (2026-11-02 battery).
            return answer
        if _completeness_contradicts(outcome.text):
            # Composition claimed a single/only gilt when the platform
            # holds a whole universe of them.
            return answer
        if _instrument_count_contradicts(answer.facts, outcome.text):
            # Composition turned one instrument's facts into "two gilt
            # instruments" - an invented second instrument.
            return answer
        if _ranking_superlative_leaks(query_text, outcome.text):
            # Composition volunteered a best/highest/top-yielding ranking
            # the user did not ask for (the "Top yielding gilt?" leak).
            return answer
        return dataclasses.replace(answer, text=outcome.text)
    return answer


@router.post("/research", status_code=status.HTTP_201_CREATED, response_model=ResearchOut)
async def create_research_answer(
    request: Request,
    body: ResearchIn,
    db: SessionDep,
    identity: IdentityDep,
    dek: DekDep,
    redis: RedisDep,
    http: HttpDep,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> JSONResponse:
    raw_body = await request.body()

    async def _handler() -> tuple[int, dict[str, Any]]:
        from app.modules.commercial.service import QuotaExceededError, enforce_quota_limit

        try:
            await enforce_quota_limit(
                db,
                account_id=identity.account_id,
                quota_key="verified_research_runs_per_month",
            )
        except QuotaExceededError as exc:
            raise TalvrinAPIError(code=ErrorCode.RIGHTS_RESTRICTED, message=str(exc)) from exc

        try:
            await research_service.append_message(
                db,
                account_id=identity.account_id,
                conversation_id=body.conversation_id,
                role=research_service.ROLE_USER,
                content=body.query,
                dek=dek,
            )
        except research_service.NotFound as exc:
            raise _not_found() from exc
        except research_service.ContentTooLong as exc:
            raise _too_long(exc) from exc

        answer = await evidence_service.assemble_research_answer(
            db,
            query_text=body.query,
            principal_id=identity.principal_id,
            account_id=identity.account_id,
            http=http,
        )
        answer = await _try_ai_composed_text(
            db,
            answer=answer,
            query_text=body.query,
            conversation_id=body.conversation_id,
            principal_id=identity.principal_id,
            account_id=identity.account_id,
            dek=dek,
            http=http,
            model=body.model,
        )

        import json
        full_content = answer.text
        metadata: dict[str, Any] = {}
        if answer.facts is not None:
            metadata["facts"] = {"title": answer.facts.title, "rows": answer.facts.rows}
        if answer.citations:
            metadata["citations"] = [
                {"label": c.label, "meta": c.meta, "pill": c.pill, "kind": c.kind, "url": c.url}
                for c in answer.citations
            ]
        if metadata:
            full_content += f"\n\n<!--METADATA\n{json.dumps(metadata)}\n-->"

        assistant_message = await research_service.append_message(
            db,
            account_id=identity.account_id,
            conversation_id=body.conversation_id,
            role=research_service.ROLE_ASSISTANT,
            content=full_content,
            dek=dek,
        )

        if answer.evidence_bundle_id is not None:
            bundle = await db.get(EvidenceBundle, answer.evidence_bundle_id)
            assert bundle is not None  # just flushed in this same transaction
            bundle.research_message_id = assistant_message.id
            bundle.status = "READY"

        await db.commit()

        response = ResearchOut(
            request_id=get_request_id(),
            generated_at=dt.datetime.now(dt.UTC),
            evidence_bundle_id=answer.evidence_bundle_id,
            allowed_output_type=answer.allowed_output_type.value,
            message_id=assistant_message.id,
            text=answer.text,
            facts=(
                FactTableOut(title=answer.facts.title, rows=answer.facts.rows)
                if answer.facts is not None
                else None
            ),
            citations=[
                CitationOut(label=c.label, meta=c.meta, pill=c.pill, kind=c.kind, url=c.url)
                for c in answer.citations
            ],
            note=answer.note,
        )
        return status.HTTP_201_CREATED, response.model_dump(mode="json")

    try:
        result = await run_idempotent(
            redis,
            scope=f"{_IDEMPOTENCY_SCOPE}:{identity.account_id}",
            idempotency_key=idempotency_key,
            request_body=raw_body,
            handler=_handler,
        )
    except IdempotencyConflictError as exc:
        raise TalvrinAPIError(code=ErrorCode.CONFLICT, message=str(exc)) from exc

    return JSONResponse(status_code=result.status_code, content=result.body)


@router.get("/research/{message_id}/evidence", response_model=EvidenceOut)
async def get_research_evidence(
    message_id: uuid.UUID,
    db: SessionDep,
    identity: IdentityDep,
) -> EvidenceOut:
    """404 for both "no such message" and "not yours" - RLS (applied per
    request via identity's session context) already makes those
    indistinguishable, same principle as chats.py's _not_found(). A message
    that exists and IS the caller's own but simply has no evidence bundle
    (e.g. an advice-redirect reply) is not an error - it returns an empty
    item list.
    """
    if not await evidence_service.is_message_visible(db, message_id=message_id):
        raise _not_found()

    detail = await evidence_service.get_evidence_for_message(db, message_id=message_id)
    await db.commit()

    if detail is None:
        return EvidenceOut(evidence_bundle_id=None, purpose_type=None, status=None, items=[])

    return EvidenceOut(
        evidence_bundle_id=detail.evidence_bundle_id,
        purpose_type=detail.purpose_type,
        status=detail.status,
        items=[
            EvidenceItemOut(
                kind=i.kind,
                subject_type=i.subject_type,
                metric_id=i.metric_id,
                value=i.value,
                basis=i.basis,
                as_of=i.as_of,
                effective_time=i.effective_time,
                source=i.source,
                permitted_use=i.permitted_use,
                document_title=i.document_title,
                text=i.text,
            )
            for i in detail.items
        ],
    )
