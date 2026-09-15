"""Conversations, projects and share links (SEC-001 §11, §15).

Every function here except `resolve_share` assumes the caller has already
applied the RLS context for the signed-in principal — the auth dependency does
that, and `identity.service.apply_rls_context` is the only place it happens.
That is deliberate: these functions never take an `account_id` from the caller
to filter on, because a query that filters by a caller-supplied account is one
typo away from filtering by the wrong one. The account is ambient, set from
the session, and enforced underneath by row-level security.

`resolve_share` is the single exception. A viewer holding a share link has no
account at all, so it reads through the SECURITY DEFINER functions from
migration 0011, which apply the share's own validity rules.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import CursorResult, Result, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uuid7 import new_uuid7
from app.modules.identity import tokens
from app.modules.research import crypto
from app.modules.research.crypto import Envelope, KeyWrapper

#: Message roles the schema's CHECK constraint accepts.
ROLE_USER = "USER"
ROLE_ASSISTANT = "ASSISTANT"
ROLE_SYSTEM = "SYSTEM"

#: Titles and names are encrypted, so length is bounded here rather than by a
#: column type. Generous enough not to annoy, tight enough to bound a row.
MAX_TITLE_LENGTH = 400
MAX_MESSAGE_LENGTH = 100_000


def _rows_affected(result: Result[Any]) -> int:
    """How many rows a DML statement touched.

    session.execute() is typed as returning Result, but a DML statement
    always yields a CursorResult, which is where rowcount lives.
    """
    return cast("CursorResult[Any]", result).rowcount


class ResearchError(Exception):
    """Base for failures safe to surface to a caller."""


class NotFound(ResearchError):
    """The row does not exist, or belongs to another account.

    The two are deliberately the same error: distinguishing them would confirm
    the existence of another tenant's conversation to anyone who guessed an id.
    """


class MissingRLSContext(ResearchError):
    """A tenant-scoped read ran on a connection with no identity set.

    This is a programming error, and the reason it is raised rather than
    tolerated is that its natural symptom is silence: with no
    `app.account_id`, every policy fails closed and the query returns zero
    rows, which looks exactly like an account that owns nothing. That bug
    shipped once already — a handler committed before reading, and since
    `set_config(..., true)` is transaction-local, the commit dropped the
    context and the endpoint returned an empty list to its own owner. Failing
    loudly is the difference between finding that in a test and finding it in
    a support ticket.
    """


class ContentTooLong(ResearchError):
    def __init__(self, field: str, limit: int) -> None:
        super().__init__(f"{field} exceeds {limit} characters")
        self.field = field
        self.limit = limit


async def _require_context(session: AsyncSession) -> uuid.UUID:
    """The account this connection is currently acting as."""
    account = (
        await session.execute(
            text("SELECT NULLIF(current_setting('app.account_id', true), '')::uuid")
        )
    ).scalar_one_or_none()
    if account is None:
        raise MissingRLSContext(
            "no app.account_id on this connection: apply_rls_context must run "
            "in the same transaction as the read"
        )
    return cast(uuid.UUID, account)


@dataclass(frozen=True)
class Project:
    id: uuid.UUID
    name: str
    created_at: dt.datetime


@dataclass(frozen=True)
class Conversation:
    id: uuid.UUID
    title: str | None
    model: str
    project_id: uuid.UUID | None
    created_at: dt.datetime
    last_message_at: dt.datetime


@dataclass(frozen=True)
class Message:
    id: uuid.UUID
    seq: int
    role: str
    content: str
    created_at: dt.datetime


@dataclass(frozen=True)
class Share:
    id: uuid.UUID
    conversation_id: uuid.UUID
    #: Only returned at creation; afterwards only the digest exists.
    token: str
    shared_up_to_seq: int
    expires_at: dt.datetime | None


@dataclass(frozen=True)
class SharedConversation:
    """What a link holder may see: a snapshot, with no owner identity."""

    conversation_id: uuid.UUID
    title: str | None
    model: str
    created_at: dt.datetime
    messages: tuple[Message, ...]


# --------------------------------------------------------------- data keys


async def account_dek(
    session: AsyncSession, *, account_id: uuid.UUID, wrapper: KeyWrapper
) -> bytes:
    """The account's data encryption key, creating one on first use.

    Returned in plaintext for the life of the request and never persisted in
    that form. Callers should fetch it once per request rather than per row:
    unwrapping is a KMS round trip in production.
    """
    existing = await _read_data_key(session, account_id)
    if existing is not None:
        return crypto.open_envelope(wrapper, existing)

    dek, envelope = crypto.create_envelope(wrapper)
    # ON CONFLICT DO NOTHING rather than catching the unique violation: a
    # failed statement aborts the whole transaction, and the only way back is
    # a rollback — which would throw away the RLS context along with it, since
    # set_config(..., true) is transaction-local. The retry would then run
    # with no identity and fail the policy's WITH CHECK. Two first requests
    # arriving together for a fresh account is not exotic; a UI that loads
    # chats and projects in parallel does it on every first sign-in.
    claimed = (
        await session.execute(
            text(
                "INSERT INTO research.account_data_key "
                "(account_id, wrapped_dek, key_name, envelope_version) "
                "VALUES (:a, :w, :k, :v) "
                "ON CONFLICT (account_id) DO NOTHING "
                "RETURNING account_id"
            ),
            {
                "a": account_id,
                "w": envelope.wrapped_dek,
                "k": envelope.key_name,
                "v": envelope.version,
            },
        )
    ).first()
    if claimed is not None:
        return dek

    # Someone else got there first. Use their key, never ours: content
    # encrypted under a discarded key would be unreadable forever.
    winner = await _read_data_key(session, account_id)
    if winner is None:
        raise ResearchError(
            "account data key conflicted on insert but is not readable"
        )
    return crypto.open_envelope(wrapper, winner)


async def _read_data_key(
    session: AsyncSession, account_id: uuid.UUID
) -> Envelope | None:
    row = (
        await session.execute(
            text(
                "SELECT wrapped_dek, key_name, envelope_version "
                "FROM research.account_data_key WHERE account_id = :a"
            ),
            {"a": account_id},
        )
    ).first()
    if row is None:
        return None
    return Envelope(
        wrapped_dek=bytes(row.wrapped_dek),
        key_name=row.key_name,
        version=row.envelope_version,
    )


# ---------------------------------------------------------------- projects


async def create_project(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    principal_id: uuid.UUID,
    name: str,
    dek: bytes,
) -> Project:
    if len(name) > MAX_TITLE_LENGTH:
        raise ContentTooLong("name", MAX_TITLE_LENGTH)
    project_id = new_uuid7()
    row = (
        await session.execute(
            text(
                "INSERT INTO research.project "
                "(id, account_id, principal_id, name) "
                "VALUES (:id, :a, :p, :n) RETURNING created_at"
            ),
            {
                "id": project_id,
                "a": account_id,
                "p": principal_id,
                "n": crypto.encrypt(dek, name),
            },
        )
    ).one()
    return Project(id=project_id, name=name, created_at=row.created_at)


async def list_projects(session: AsyncSession, *, dek: bytes) -> list[Project]:
    await _require_context(session)
    rows = (
        await session.execute(
            text(
                "SELECT id, name, created_at FROM research.project "
                "WHERE deleted_at IS NULL ORDER BY created_at"
            )
        )
    ).all()
    return [
        Project(
            id=r.id,
            name=crypto.decrypt(dek, bytes(r.name)),
            created_at=r.created_at,
        )
        for r in rows
    ]


async def rename_project(
    session: AsyncSession, *, project_id: uuid.UUID, name: str, dek: bytes
) -> None:
    if len(name) > MAX_TITLE_LENGTH:
        raise ContentTooLong("name", MAX_TITLE_LENGTH)
    result = await session.execute(
        text(
            "UPDATE research.project SET name = :n, updated_at = now() "
            "WHERE id = :id AND deleted_at IS NULL"
        ),
        {"n": crypto.encrypt(dek, name), "id": project_id},
    )
    if _rows_affected(result) == 0:
        raise NotFound(str(project_id))


async def delete_project(session: AsyncSession, *, project_id: uuid.UUID) -> None:
    """Soft delete. Conversations inside it survive, unfiled — losing a chat
    because its folder was deleted would be a surprising amount of damage for
    one click."""
    result = await session.execute(
        text(
            "UPDATE research.project SET deleted_at = now() "
            "WHERE id = :id AND deleted_at IS NULL"
        ),
        {"id": project_id},
    )
    if _rows_affected(result) == 0:
        raise NotFound(str(project_id))
    await session.execute(
        text(
            "UPDATE research.conversation SET project_id = NULL "
            "WHERE project_id = :id"
        ),
        {"id": project_id},
    )


# ----------------------------------------------------------- conversations


async def _assert_project_visible(
    session: AsyncSession, project_id: uuid.UUID | None
) -> None:
    """Rejects a project that is not ours, before the database has to.

    Migration 0011's trigger is the real guarantee — a foreign key ignores RLS,
    so nothing but an explicit check stops a conversation pointing at another
    tenant's project. But a trigger raises a raw database error; this turns the
    ordinary case into the same NotFound every other lookup produces, without
    the trigger ceasing to be the thing that actually holds the line.
    """
    if project_id is None:
        return
    found = (
        await session.execute(
            text(
                "SELECT 1 FROM research.project "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": project_id},
        )
    ).first()
    if found is None:
        raise NotFound(str(project_id))


async def create_conversation(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    principal_id: uuid.UUID,
    model: str,
    title: str | None = None,
    project_id: uuid.UUID | None = None,
    dek: bytes,
) -> Conversation:
    if title is not None and len(title) > MAX_TITLE_LENGTH:
        raise ContentTooLong("title", MAX_TITLE_LENGTH)
    await _assert_project_visible(session, project_id)
    conversation_id = new_uuid7()
    row = (
        await session.execute(
            text(
                "INSERT INTO research.conversation "
                "(id, account_id, principal_id, project_id, title, model) "
                "VALUES (:id, :a, :p, :proj, :t, :m) "
                "RETURNING created_at, last_message_at"
            ),
            {
                "id": conversation_id,
                "a": account_id,
                "p": principal_id,
                "proj": project_id,
                "t": crypto.encrypt(dek, title) if title is not None else None,
                "m": model,
            },
        )
    ).one()
    return Conversation(
        id=conversation_id,
        title=title,
        model=model,
        project_id=project_id,
        created_at=row.created_at,
        last_message_at=row.last_message_at,
    )


async def list_conversations(
    session: AsyncSession, *, dek: bytes, limit: int = 200
) -> list[Conversation]:
    await _require_context(session)
    rows = (
        await session.execute(
            text(
                "SELECT id, title, model, project_id, created_at, last_message_at "
                "FROM research.conversation WHERE deleted_at IS NULL "
                "ORDER BY last_message_at DESC LIMIT :lim"
            ),
            {"lim": limit},
        )
    ).all()
    return [_conversation_from_row(r, dek) for r in rows]


async def get_conversation(
    session: AsyncSession, *, conversation_id: uuid.UUID, dek: bytes
) -> Conversation:
    await _require_context(session)
    row = (
        await session.execute(
            text(
                "SELECT id, title, model, project_id, created_at, last_message_at "
                "FROM research.conversation "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": conversation_id},
        )
    ).first()
    if row is None:
        raise NotFound(str(conversation_id))
    return _conversation_from_row(row, dek)


def _conversation_from_row(row: Any, dek: bytes) -> Conversation:
    return Conversation(
        id=row.id,
        title=crypto.decrypt(dek, bytes(row.title)) if row.title is not None else None,
        model=row.model,
        project_id=row.project_id,
        created_at=row.created_at,
        last_message_at=row.last_message_at,
    )


async def rename_conversation(
    session: AsyncSession, *, conversation_id: uuid.UUID, title: str, dek: bytes
) -> None:
    if len(title) > MAX_TITLE_LENGTH:
        raise ContentTooLong("title", MAX_TITLE_LENGTH)
    result = await session.execute(
        text(
            "UPDATE research.conversation SET title = :t "
            "WHERE id = :id AND deleted_at IS NULL"
        ),
        {"t": crypto.encrypt(dek, title), "id": conversation_id},
    )
    if _rows_affected(result) == 0:
        raise NotFound(str(conversation_id))


async def move_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    project_id: uuid.UUID | None,
) -> None:
    await _assert_project_visible(session, project_id)
    result = await session.execute(
        text(
            "UPDATE research.conversation SET project_id = :proj "
            "WHERE id = :id AND deleted_at IS NULL"
        ),
        {"proj": project_id, "id": conversation_id},
    )
    if _rows_affected(result) == 0:
        raise NotFound(str(conversation_id))


async def delete_conversation(
    session: AsyncSession, *, conversation_id: uuid.UUID
) -> None:
    """Soft delete, and revoke every share in the same breath.

    A link handed out earlier must stop working the moment the conversation is
    deleted; leaving live shares pointing at deleted content would make
    deletion cosmetic.
    """
    result = await session.execute(
        text(
            "UPDATE research.conversation SET deleted_at = now() "
            "WHERE id = :id AND deleted_at IS NULL"
        ),
        {"id": conversation_id},
    )
    if _rows_affected(result) == 0:
        raise NotFound(str(conversation_id))
    await session.execute(
        text(
            "UPDATE research.conversation_share SET revoked_at = now() "
            "WHERE conversation_id = :id AND revoked_at IS NULL"
        ),
        {"id": conversation_id},
    )


# ---------------------------------------------------------------- messages


async def append_message(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    dek: bytes,
) -> Message:
    if role not in (ROLE_USER, ROLE_ASSISTANT, ROLE_SYSTEM):
        raise ResearchError(f"unknown role {role!r}")
    if len(content) > MAX_MESSAGE_LENGTH:
        raise ContentTooLong("content", MAX_MESSAGE_LENGTH)

    # Confirms the conversation is ours before writing: RLS would block the
    # message insert anyway, but the failure would be an integrity error rather
    # than a clean 404.
    exists = (
        await session.execute(
            text(
                "SELECT 1 FROM research.conversation "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": conversation_id},
        )
    ).first()
    if exists is None:
        raise NotFound(str(conversation_id))

    message_id = new_uuid7()
    # seq is assigned in the same statement that inserts, so two concurrent
    # appends cannot read the same maximum. If they race anyway, the
    # (conversation_id, seq) unique constraint rejects the loser rather than
    # silently interleaving.
    row = (
        await session.execute(
            text(
                "INSERT INTO research.message "
                "(id, conversation_id, account_id, seq, role, content) "
                "SELECT :id, :c, :a, "
                "       COALESCE(MAX(m.seq), 0) + 1, :r, :body "
                "FROM research.message AS m WHERE m.conversation_id = :c "
                "RETURNING seq, created_at"
            ),
            {
                "id": message_id,
                "c": conversation_id,
                "a": account_id,
                "r": role,
                "body": crypto.encrypt(
                    dek, content, aad=crypto.conversation_aad(conversation_id)
                ),
            },
        )
    ).one()

    await session.execute(
        text(
            "UPDATE research.conversation SET last_message_at = now() WHERE id = :id"
        ),
        {"id": conversation_id},
    )
    return Message(
        id=message_id,
        seq=row.seq,
        role=role,
        content=content,
        created_at=row.created_at,
    )


async def list_messages(
    session: AsyncSession, *, conversation_id: uuid.UUID, dek: bytes
) -> list[Message]:
    await _require_context(session)
    rows = (
        await session.execute(
            text(
                "SELECT m.id, m.seq, m.role, m.content, m.created_at "
                "FROM research.message AS m "
                "JOIN research.conversation AS c ON c.id = m.conversation_id "
                "WHERE m.conversation_id = :id AND c.deleted_at IS NULL "
                "ORDER BY m.seq"
            ),
            {"id": conversation_id},
        )
    ).all()
    aad = crypto.conversation_aad(conversation_id)
    return [
        Message(
            id=r.id,
            seq=r.seq,
            role=r.role,
            content=crypto.decrypt(dek, bytes(r.content), aad=aad),
            created_at=r.created_at,
        )
        for r in rows
    ]


# ------------------------------------------------------------------ shares


async def create_share(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    principal_id: uuid.UUID,
    conversation_id: uuid.UUID,
    expires_at: dt.datetime | None = None,
) -> Share:
    """Mints a link. The raw token is returned once and never stored.

    The share is pinned to the conversation's current length, so continuing the
    chat afterwards does not widen what the link exposes.
    """
    head = (
        await session.execute(
            text(
                "SELECT COALESCE(MAX(m.seq), 0) AS head "
                "FROM research.conversation AS c "
                "LEFT JOIN research.message AS m ON m.conversation_id = c.id "
                "WHERE c.id = :id AND c.deleted_at IS NULL "
                "GROUP BY c.id"
            ),
            {"id": conversation_id},
        )
    ).first()
    if head is None:
        raise NotFound(str(conversation_id))

    token = tokens.generate_token()
    share_id = new_uuid7()
    await session.execute(
        text(
            "INSERT INTO research.conversation_share "
            "(id, conversation_id, account_id, created_by_principal_id, "
            " token_hash, shared_up_to_seq, expires_at) "
            "VALUES (:id, :c, :a, :p, :h, :seq, :exp)"
        ),
        {
            "id": share_id,
            "c": conversation_id,
            "a": account_id,
            "p": principal_id,
            "h": tokens.hash_token(token),
            "seq": head.head,
            "exp": expires_at,
        },
    )
    return Share(
        id=share_id,
        conversation_id=conversation_id,
        token=token,
        shared_up_to_seq=head.head,
        expires_at=expires_at,
    )


async def revoke_share(session: AsyncSession, *, share_id: uuid.UUID) -> None:
    result = await session.execute(
        text(
            "UPDATE research.conversation_share SET revoked_at = now() "
            "WHERE id = :id AND revoked_at IS NULL"
        ),
        {"id": share_id},
    )
    if _rows_affected(result) == 0:
        raise NotFound(str(share_id))


async def list_shares(
    session: AsyncSession, *, conversation_id: uuid.UUID
) -> list[tuple[uuid.UUID, dt.datetime, dt.datetime | None]]:
    await _require_context(session)
    rows = (
        await session.execute(
            text(
                "SELECT id, created_at, expires_at "
                "FROM research.conversation_share "
                "WHERE conversation_id = :id AND revoked_at IS NULL "
                "ORDER BY created_at DESC"
            ),
            {"id": conversation_id},
        )
    ).all()
    return [(r.id, r.created_at, r.expires_at) for r in rows]


async def resolve_share(
    session: AsyncSession, *, token: str, wrapper: KeyWrapper
) -> SharedConversation | None:
    """Reads a shared conversation for a viewer with no account.

    The only path in this module that does not rely on the caller's RLS
    context, because there isn't one. Validity — revoked, expired, deleted,
    sequence bound — is enforced inside the definer functions as well as here.
    """
    digest = tokens.hash_token(token)
    header = (
        await session.execute(
            text(
                "SELECT conversation_id, title, model, account_id, created_at, "
                "wrapped_dek, key_name, envelope_version "
                "FROM research.lookup_shared_conversation(:h)"
            ),
            {"h": digest},
        )
    ).first()
    if header is None:
        return None

    # The owner's key arrives wrapped, from the same definer call that
    # validated the token — a plain read of account_data_key would be blocked
    # by RLS here, correctly, since this caller has no account. Unwrapping is a
    # key operation the application is permitted to perform; it grants nothing
    # beyond the messages the share itself returns.
    dek = crypto.open_envelope(
        wrapper,
        Envelope(
            wrapped_dek=bytes(header.wrapped_dek),
            key_name=header.key_name,
            version=header.envelope_version,
        ),
    )

    rows = (
        await session.execute(
            text(
                "SELECT message_id, seq, role, content, created_at "
                "FROM research.lookup_shared_messages(:h)"
            ),
            {"h": digest},
        )
    ).all()
    aad = crypto.conversation_aad(header.conversation_id)
    messages = tuple(
        Message(
            id=r.message_id,
            seq=r.seq,
            role=r.role,
            content=crypto.decrypt(dek, bytes(r.content), aad=aad),
            created_at=r.created_at,
        )
        for r in rows
    )
    return SharedConversation(
        conversation_id=header.conversation_id,
        title=(
            crypto.decrypt(dek, bytes(header.title))
            if header.title is not None
            else None
        ),
        model=header.model,
        created_at=header.created_at,
        messages=messages,
    )
