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
"""

from __future__ import annotations

import dataclasses
import datetime as dt
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

_IDEMPOTENCY_SCOPE = "POST /api/v1/research"


class ResearchIn(BaseModel):
    conversation_id: uuid.UUID
    query: str = Field(min_length=1, max_length=research_service.MAX_MESSAGE_LENGTH)


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

    conversation = await research_service.get_conversation(
        db, conversation_id=conversation_id, dek=dek
    )
    settings = get_settings()
    api_keys = {
        code: key
        for code, key in {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key}.items()
        if key
    }

    outcome = await invoke_model(
        db,
        task_type=conversation.model,
        evidence_bundle_id=answer.evidence_bundle_id,
        instruction=query_text,
        http=http,
        api_keys=api_keys,
        principal_id=principal_id,
        account_id=account_id,
        jurisdiction_code=DEV_JURISDICTION,
        requested_output_type=answer.allowed_output_type,
    )
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
            scope=_IDEMPOTENCY_SCOPE,
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
                document_title=i.document_title,
                text=i.text,
            )
            for i in detail.items
        ],
    )
