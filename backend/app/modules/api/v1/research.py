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

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.errors import ErrorCode, TalvrinAPIError
from app.core.idempotency import IdempotencyConflictError, run_idempotent
from app.core.request_context import get_request_id
from app.modules.api.v1.deps import DekDep, IdentityDep, RedisDep, SessionDep
from app.modules.evidence import service as evidence_service
from app.modules.evidence.models import EvidenceBundle
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


def _not_found() -> TalvrinAPIError:
    return TalvrinAPIError(code=ErrorCode.NOT_FOUND, message="Not found.")


def _too_long(exc: research_service.ContentTooLong) -> TalvrinAPIError:
    return TalvrinAPIError(code=ErrorCode.VALIDATION_ERROR, message=str(exc))


@router.post("/research", status_code=status.HTTP_201_CREATED, response_model=ResearchOut)
async def create_research_answer(
    request: Request,
    body: ResearchIn,
    db: SessionDep,
    identity: IdentityDep,
    dek: DekDep,
    redis: RedisDep,
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
        )

        assistant_message = await research_service.append_message(
            db,
            account_id=identity.account_id,
            conversation_id=body.conversation_id,
            role=research_service.ROLE_ASSISTANT,
            content=answer.text,
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
                CitationOut(label=c.label, meta=c.meta, pill=c.pill, kind=c.kind)
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
