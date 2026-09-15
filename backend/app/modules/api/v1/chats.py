"""Conversation, project and sharing endpoints (API-001 shape).

Nothing here takes an account from the caller. The account comes from the
session via `current_identity`, and row-level security enforces it underneath,
so a handler cannot be tricked into operating on someone else's rows by a
crafted body.

Failures to find a row are reported as 404 whether the row is absent or simply
belongs to another account — see `service.NotFound`.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.core.errors import ErrorCode, TalvrinAPIError
from app.modules.api.v1.deps import DekDep, IdentityDep, SessionDep, WrapperDep
from app.modules.research import crypto, service

router = APIRouter(tags=["research"])

#: Model identifiers the UI offers. Validated here so an unknown value cannot
#: be persisted and then surprise a later reader.
ALLOWED_MODELS = frozenset({"talvrin-go", "talvrin-pro"})


def _not_found() -> TalvrinAPIError:
    """Deliberately says nothing about why.

    Absent and not-yours must be indistinguishable, or the endpoint becomes
    a way to test whether an identifier exists in another account.
    """
    return TalvrinAPIError(code=ErrorCode.NOT_FOUND, message="Not found.")


def _too_long(exc: service.ContentTooLong) -> TalvrinAPIError:
    return TalvrinAPIError(code=ErrorCode.VALIDATION_ERROR, message=str(exc))


def _unreadable() -> TalvrinAPIError:
    """Stored content did not decrypt.

    The expected cause is SEC-001 §15.2 cryptographic erasure: the
    account's wrapped data key was destroyed, so its ciphertext is gone for
    good. Reported distinctly from a generic 500 because it is a known,
    explainable state rather than a crash — though it is not in fact
    retryable, which the shared DATA_UNAVAILABLE code implies.
    """
    return TalvrinAPIError(
        code=ErrorCode.DATA_UNAVAILABLE,
        message="This content could not be decrypted.",
    )


# ------------------------------------------------------------------ schemas


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=service.MAX_TITLE_LENGTH)


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: dt.datetime


class ConversationIn(BaseModel):
    model: str = "talvrin-go"
    title: str | None = Field(default=None, max_length=service.MAX_TITLE_LENGTH)
    project_id: uuid.UUID | None = None


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=service.MAX_TITLE_LENGTH)
    #: Present-and-null means "remove from its project", so the field is
    #: distinguished from absent by `model_fields_set`.
    project_id: uuid.UUID | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    model: str
    project_id: uuid.UUID | None
    created_at: dt.datetime
    last_message_at: dt.datetime


class MessageIn(BaseModel):
    """A message from the person typing.

    There is deliberately no `role` field. A client that could post an
    ASSISTANT message could fabricate something Talvrin never said — and then
    share the link, where it would read as the platform's own output. For a
    product whose whole claim is sourced research and no recommendations, that
    is the forgery worth designing out rather than policing later. Assistant
    and system turns are written by the server, through the service layer.
    """

    content: str = Field(min_length=1, max_length=service.MAX_MESSAGE_LENGTH)


class MessageOut(BaseModel):
    id: uuid.UUID
    seq: int
    role: str
    content: str
    created_at: dt.datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class ShareIn(BaseModel):
    expires_at: dt.datetime | None = None


class ShareOut(BaseModel):
    id: uuid.UUID
    #: Returned exactly once, at creation. Not recoverable afterwards.
    token: str
    shared_up_to_seq: int
    expires_at: dt.datetime | None


class ShareSummaryOut(BaseModel):
    id: uuid.UUID
    created_at: dt.datetime
    expires_at: dt.datetime | None


class SharedViewOut(BaseModel):
    """What a link holder sees. Carries no owner identity by design."""

    conversation_id: uuid.UUID
    title: str | None
    model: str
    created_at: dt.datetime
    messages: list[MessageOut]


def _project_out(p: service.Project) -> ProjectOut:
    return ProjectOut(id=p.id, name=p.name, created_at=p.created_at)


def _conversation_out(c: service.Conversation) -> ConversationOut:
    return ConversationOut(
        id=c.id,
        title=c.title,
        model=c.model,
        project_id=c.project_id,
        created_at=c.created_at,
        last_message_at=c.last_message_at,
    )


def _message_out(m: service.Message) -> MessageOut:
    return MessageOut(
        id=m.id, seq=m.seq, role=m.role, content=m.content, created_at=m.created_at
    )


# ----------------------------------------------------------------- projects


@router.get("/projects")
async def list_projects(
    db: SessionDep, identity: IdentityDep, dek: DekDep
) -> list[ProjectOut]:
    # Read first, commit second. The RLS context is transaction-local, so
    # committing beforehand drops it and every row is then filtered out —
    # which reads as "no projects" rather than as an error.
    try:
        projects = await service.list_projects(db, dek=dek)
    except crypto.DecryptionFailed as exc:
        raise _unreadable() from exc
    await db.commit()
    return [_project_out(p) for p in projects]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectIn, db: SessionDep, identity: IdentityDep, dek: DekDep
) -> ProjectOut:
    try:
        project = await service.create_project(
            db,
            account_id=identity.account_id,
            principal_id=identity.principal_id,
            name=body.name,
            dek=dek,
        )
    except service.ContentTooLong as exc:
        raise _too_long(exc) from exc
    await db.commit()
    return _project_out(project)


@router.patch("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def rename_project(
    project_id: uuid.UUID,
    body: ProjectIn,
    db: SessionDep,
    identity: IdentityDep,
    dek: DekDep,
) -> None:
    try:
        await service.rename_project(
            db, project_id=project_id, name=body.name, dek=dek
        )
    except service.NotFound as exc:
        raise _not_found() from exc
    except service.ContentTooLong as exc:
        raise _too_long(exc) from exc
    await db.commit()


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID, db: SessionDep, identity: IdentityDep
) -> None:
    try:
        await service.delete_project(db, project_id=project_id)
    except service.NotFound as exc:
        raise _not_found() from exc
    await db.commit()


# ------------------------------------------------------------------- chats


@router.get("/chats")
async def list_chats(
    db: SessionDep, identity: IdentityDep, dek: DekDep
) -> list[ConversationOut]:
    try:
        conversations = await service.list_conversations(db, dek=dek)
    except crypto.DecryptionFailed as exc:
        raise _unreadable() from exc
    await db.commit()
    return [_conversation_out(c) for c in conversations]


@router.post("/chats", status_code=status.HTTP_201_CREATED)
async def create_chat(
    body: ConversationIn, db: SessionDep, identity: IdentityDep, dek: DekDep
) -> ConversationOut:
    if body.model not in ALLOWED_MODELS:
        raise TalvrinAPIError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Unknown model {body.model!r}.",
        )
    try:
        conversation = await service.create_conversation(
            db,
            account_id=identity.account_id,
            principal_id=identity.principal_id,
            model=body.model,
            title=body.title,
            project_id=body.project_id,
            dek=dek,
        )
    except service.NotFound as exc:
        raise _not_found() from exc
    except service.ContentTooLong as exc:
        raise _too_long(exc) from exc
    await db.commit()
    return _conversation_out(conversation)


@router.get("/chats/{chat_id}")
async def get_chat(
    chat_id: uuid.UUID, db: SessionDep, identity: IdentityDep, dek: DekDep
) -> ConversationDetailOut:
    try:
        conversation = await service.get_conversation(
            db, conversation_id=chat_id, dek=dek
        )
        messages = await service.list_messages(
            db, conversation_id=chat_id, dek=dek
        )
    except service.NotFound as exc:
        raise _not_found() from exc
    except crypto.DecryptionFailed as exc:
        raise _unreadable() from exc
    await db.commit()
    return ConversationDetailOut(
        **_conversation_out(conversation).model_dump(),
        messages=[_message_out(m) for m in messages],
    )


@router.patch("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def patch_chat(
    chat_id: uuid.UUID,
    body: ConversationPatch,
    db: SessionDep,
    identity: IdentityDep,
    dek: DekDep,
) -> None:
    fields = body.model_fields_set
    try:
        if "title" in fields and body.title is not None:
            await service.rename_conversation(
                db, conversation_id=chat_id, title=body.title, dek=dek
            )
        if "project_id" in fields:
            await service.move_conversation(
                db, conversation_id=chat_id, project_id=body.project_id
            )
    except service.NotFound as exc:
        raise _not_found() from exc
    except service.ContentTooLong as exc:
        raise _too_long(exc) from exc
    await db.commit()


@router.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: uuid.UUID, db: SessionDep, identity: IdentityDep
) -> None:
    try:
        await service.delete_conversation(db, conversation_id=chat_id)
    except service.NotFound as exc:
        raise _not_found() from exc
    await db.commit()


@router.post("/chats/{chat_id}/messages", status_code=status.HTTP_201_CREATED)
async def append_message(
    chat_id: uuid.UUID,
    body: MessageIn,
    db: SessionDep,
    identity: IdentityDep,
    dek: DekDep,
) -> MessageOut:
    try:
        message = await service.append_message(
            db,
            account_id=identity.account_id,
            conversation_id=chat_id,
            role=service.ROLE_USER,
            content=body.content,
            dek=dek,
        )
    except service.NotFound as exc:
        raise _not_found() from exc
    except service.ContentTooLong as exc:
        raise _too_long(exc) from exc
    except service.ResearchError as exc:
        raise TalvrinAPIError(
            code=ErrorCode.VALIDATION_ERROR, message=str(exc)
        ) from exc
    await db.commit()
    return _message_out(message)


# ------------------------------------------------------------------ shares


@router.post("/chats/{chat_id}/share", status_code=status.HTTP_201_CREATED)
async def create_share(
    chat_id: uuid.UUID,
    body: ShareIn,
    db: SessionDep,
    identity: IdentityDep,
) -> ShareOut:
    try:
        share = await service.create_share(
            db,
            account_id=identity.account_id,
            principal_id=identity.principal_id,
            conversation_id=chat_id,
            expires_at=body.expires_at,
        )
    except service.NotFound as exc:
        raise _not_found() from exc
    await db.commit()
    return ShareOut(
        id=share.id,
        token=share.token,
        shared_up_to_seq=share.shared_up_to_seq,
        expires_at=share.expires_at,
    )


@router.get("/chats/{chat_id}/shares")
async def list_shares(
    chat_id: uuid.UUID, db: SessionDep, identity: IdentityDep
) -> list[ShareSummaryOut]:
    rows = await service.list_shares(db, conversation_id=chat_id)
    await db.commit()
    return [
        ShareSummaryOut(id=i, created_at=created, expires_at=expires)
        for i, created, expires in rows
    ]


@router.delete("/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share(
    share_id: uuid.UUID, db: SessionDep, identity: IdentityDep
) -> None:
    try:
        await service.revoke_share(db, share_id=share_id)
    except service.NotFound as exc:
        raise _not_found() from exc
    await db.commit()


@router.get("/shared/{token}")
async def read_shared(
    token: str, db: SessionDep, wrapper: WrapperDep
) -> SharedViewOut:
    """Public. Deliberately takes no identity: the token is the whole
    authorisation, and signing in must not change what a link shows."""
    try:
        view = await service.resolve_share(db, token=token, wrapper=wrapper)
    except crypto.DecryptionFailed as exc:
        raise _unreadable() from exc
    await db.commit()
    if view is None:
        raise TalvrinAPIError(
            code=ErrorCode.NOT_FOUND,
            message="This link is no longer available.",
        )
    return SharedViewOut(
        conversation_id=view.conversation_id,
        title=view.title,
        model=view.model,
        created_at=view.created_at,
        messages=[_message_out(m) for m in view.messages],
    )
