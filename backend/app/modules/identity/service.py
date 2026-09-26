"""Authentication service (SEC-001 §5–§9).

Credentials are Supabase's problem now (`supabase_auth.py`): password
storage, hashing, and verification all happen on their side, over TLS, and
this module never sees a stored hash. What stays here, unchanged from before
that split, are the properties SEC-001 actually cares about at *this* layer:

1. **No account enumeration** (§7.1). `supabase_auth.sign_in_with_password`
   already collapses "wrong password" and "unknown address" into one
   `InvalidCredentials`, so nothing here has to reconstruct that property —
   it just has to not undo it.

2. **Sessions are server-side rows** (§8), not self-contained signed tokens,
   because revocation has to be immediate and absolute. The cookie carries a
   random token; only its digest is stored. This is entirely local — it has
   nothing to do with Supabase's own session/refresh tokens, which this
   backend never stores or forwards to the browser at all.

3. **RLS is never bypassed wholesale.** The one read that must happen before
   an identity exists — resolving a Supabase user id to a local principal —
   goes through the SECURITY DEFINER function from migration 0012. Everything
   after that runs with `app.account_id` and `app.principal_id` set, so
   ordinary policies apply.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.uuid7 import new_uuid7
from app.modules.identity import supabase_auth, tokens


class AuthError(Exception):
    """Base for failures that are safe to surface to a caller."""


class InvalidCredentials(AuthError):
    """Deliberately vague — see the no-enumeration rule above."""


class EmailAlreadyRegistered(AuthError):
    """Only ever raised on sign-up, never on sign-in."""


class WeakPassword(AuthError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidResetToken(AuthError):
    """The recovery link's token was missing, malformed, expired, or already
    used to reset a password once already."""


class EmailNotConfirmed(AuthError):
    """Only reachable if Supabase email confirmation is switched back on —
    see supabase_auth.EmailNotConfirmed. The product runs with confirmation
    disabled so sign-up can sign a user in immediately, but a login attempt
    must still handle this honestly rather than mislabel it as a wrong
    password if that setting ever changes."""


@dataclass(frozen=True)
class Identity:
    """Who a request is acting as."""

    principal_id: uuid.UUID
    account_id: uuid.UUID
    email: str


@dataclass(frozen=True)
class IssuedLogin:
    identity: Identity
    session_id: uuid.UUID
    #: Raw token for the cookie. Never persisted, never logged.
    token: str
    absolute_expiry: dt.datetime


def normalise_email(email: str) -> str:
    """Lower-cased and trimmed. The unique index is on `lower(email)`, so the
    application must agree with it or inserts fail confusingly."""
    return email.strip().lower()


async def apply_rls_context(
    session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID
) -> None:
    """Sets the GUCs the identity policies read.

    `is_local => true` scopes them to the current transaction, so a pooled
    connection cannot carry one request's identity into the next — the single
    most dangerous failure mode of GUC-based RLS.
    """
    await session.execute(
        text("SELECT set_config('app.account_id', :a, true)"), {"a": str(account_id)}
    )
    await session.execute(
        text("SELECT set_config('app.principal_id', :p, true)"),
        {"p": str(principal_id)},
    )


async def _find_local_principal(
    session: AsyncSession, *, supabase_user_id: uuid.UUID
) -> Identity | None:
    row = (
        await session.execute(
            text(
                "SELECT principal_id, account_id, email, status "
                "FROM identity.lookup_principal_by_supabase_id(:s)"
            ),
            {"s": supabase_user_id},
        )
    ).first()
    if row is None or row.status != "ACTIVE":
        return None
    return Identity(principal_id=row.principal_id, account_id=row.account_id, email=row.email)


async def _create_local_principal(
    session: AsyncSession, *, supabase_user_id: uuid.UUID, email: str
) -> Identity:
    """Mirrors a Supabase user into `identity.account`/`identity.principal`.

    Called both right after sign-up and, defensively, on a sign-in that
    finds no matching local row — a user created directly in the Supabase
    dashboard, or one from before this account existed locally, should still
    be able to sign in rather than hit an opaque failure the first time.
    """
    account_id = new_uuid7()
    principal_id = new_uuid7()

    # identity.account has no RLS; principal does, so the context has to be
    # in place before the insert or its WITH CHECK rejects our own row.
    await session.execute(
        text(
            "INSERT INTO identity.account (id, name, status) "
            "VALUES (:id, :name, 'ACTIVE')"
        ),
        {"id": account_id, "name": email},
    )
    await apply_rls_context(session, account_id=account_id, principal_id=principal_id)
    await session.execute(
        text(
            "INSERT INTO identity.principal "
            "(id, account_id, email, status, supabase_user_id) "
            "VALUES (:id, :account_id, :email, 'ACTIVE', :sub)"
        ),
        {
            "id": principal_id,
            "account_id": account_id,
            "email": email,
            "sub": supabase_user_id,
        },
    )
    return Identity(principal_id=principal_id, account_id=account_id, email=email)


async def register(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    http: httpx.AsyncClient,
    settings: Settings | None = None,
) -> IssuedLogin:
    """Creates the account in Supabase, mirrors it locally, and signs in.

    `http` is caller-supplied rather than a module-level client for the same
    reason `market/connectors/dmo_gilts/client.py` takes one: production
    injects a real client via FastAPI's dependency, tests inject one backed
    by a fake transport, and this function does not need to know which.
    """
    address = normalise_email(email)
    cfg = settings or get_settings()

    try:
        user = await supabase_auth.sign_up(http, email=address, password=password, settings=cfg)
    except supabase_auth.EmailAlreadyRegistered as exc:
        raise EmailAlreadyRegistered(address) from exc
    except supabase_auth.WeakPassword as exc:
        raise WeakPassword(exc.reason) from exc

    identity = await _create_local_principal(
        session, supabase_user_id=user.id, email=user.email
    )
    return await _issue_session(session, identity)


async def authenticate(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    http: httpx.AsyncClient,
    settings: Settings | None = None,
) -> IssuedLogin:
    """Verifies credentials against Supabase and starts a local session.

    Raises InvalidCredentials for a wrong password or an unknown address —
    Supabase's own error code already collapses the two — and
    EmailNotConfirmed only if confirmation is switched back on.
    """
    address = normalise_email(email)
    cfg = settings or get_settings()

    try:
        user = await supabase_auth.sign_in_with_password(
            http, email=address, password=password, settings=cfg
        )
    except supabase_auth.InvalidCredentials as exc:
        raise InvalidCredentials from exc
    except supabase_auth.EmailNotConfirmed as exc:
        raise EmailNotConfirmed from exc

    identity = await _find_local_principal(session, supabase_user_id=user.id)
    if identity is None:
        identity = await _create_local_principal(
            session, supabase_user_id=user.id, email=user.email
        )
    else:
        await apply_rls_context(
            session, account_id=identity.account_id, principal_id=identity.principal_id
        )

    return await _issue_session(session, identity)


async def complete_password_reset(
    session: AsyncSession,
    *,
    access_token: str,
    new_password: str,
    http: httpx.AsyncClient,
    settings: Settings | None = None,
) -> IssuedLogin:
    """Sets the new password, then signs the user straight in.

    The reset link already proves the person clicking it controls the
    mailbox on file — that is a stronger check than a password would be, so
    there is no reason to make them type the new password twice in two
    separate steps. Confirmed live: PUT /auth/v1/user with the recovery
    token's bearer changes the credential immediately, and a fresh
    password-grant login with the new password succeeds right after.
    """
    cfg = settings or get_settings()
    try:
        user = await supabase_auth.update_password(
            http, access_token=access_token, new_password=new_password, settings=cfg
        )
    except supabase_auth.InvalidResetToken as exc:
        raise InvalidResetToken from exc
    except supabase_auth.WeakPassword as exc:
        raise WeakPassword(exc.reason) from exc

    identity = await _find_local_principal(session, supabase_user_id=user.id)
    if identity is None:
        identity = await _create_local_principal(
            session, supabase_user_id=user.id, email=user.email
        )
    else:
        await apply_rls_context(
            session, account_id=identity.account_id, principal_id=identity.principal_id
        )

    return await _issue_session(session, identity)


async def request_password_reset(
    *,
    email: str,
    http: httpx.AsyncClient,
    settings: Settings | None = None,
    redirect_to: str | None = None,
) -> None:
    """Asks Supabase to send a reset email. Never raises for an unknown
    address — see supabase_auth.request_password_reset."""
    await supabase_auth.request_password_reset(
        http,
        email=normalise_email(email),
        settings=settings or get_settings(),
        redirect_to=redirect_to,
    )


async def _issue_session(session: AsyncSession, identity: Identity) -> IssuedLogin:
    """Mints a session row. Assumes the RLS context is already applied."""
    issued = tokens.issue_session()
    session_id = new_uuid7()
    await session.execute(
        text(
            "INSERT INTO identity.session "
            "(id, principal_id, token_hash, expires_at, idle_expires_at) "
            "VALUES (:id, :pid, :hash, :abs, :idle)"
        ),
        {
            "id": session_id,
            "pid": identity.principal_id,
            "hash": issued.token_hash,
            "abs": issued.absolute_expiry,
            "idle": issued.idle_expiry,
        },
    )
    return IssuedLogin(
        identity=identity,
        session_id=session_id,
        token=issued.token,
        absolute_expiry=issued.absolute_expiry,
    )


async def resolve_session(
    session: AsyncSession, *, token: str, now: dt.datetime | None = None
) -> Identity | None:
    """Turns a cookie value into an identity, or None.

    Also slides the idle window on success, which is what makes an active
    session survive while an abandoned one lapses.
    """
    moment = now or dt.datetime.now(dt.UTC)
    row = (
        await session.execute(
            text(
                "SELECT session_id, principal_id, account_id, email, "
                "principal_status, expires_at, idle_expires_at, revoked_at "
                "FROM identity.lookup_session_by_token(:h)"
            ),
            {"h": tokens.hash_token(token)},
        )
    ).first()
    if row is None:
        return None

    if tokens.is_expired(
        absolute_expiry=row.expires_at,
        idle_expiry=row.idle_expires_at or row.expires_at,
        revoked_at=row.revoked_at,
        now=moment,
    ):
        return None
    if row.principal_status != "ACTIVE":
        return None

    identity = Identity(
        principal_id=row.principal_id, account_id=row.account_id, email=row.email
    )
    await apply_rls_context(
        session, account_id=identity.account_id, principal_id=identity.principal_id
    )
    await session.execute(
        text("UPDATE identity.session SET idle_expires_at = :i WHERE id = :id"),
        {
            "i": tokens.slide_idle_expiry(
                absolute_expiry=row.expires_at, now=moment
            ),
            "id": row.session_id,
        },
    )
    return identity


async def revoke_session(session: AsyncSession, *, token: str) -> None:
    """Signs out. Idempotent: an unknown or already-revoked token is not an
    error, because a caller clearing a stale cookie has done nothing wrong."""
    row = (
        await session.execute(
            text(
                "SELECT session_id, principal_id, account_id "
                "FROM identity.lookup_session_by_token(:h)"
            ),
            {"h": tokens.hash_token(token)},
        )
    ).first()
    if row is None:
        return
    await apply_rls_context(
        session, account_id=row.account_id, principal_id=row.principal_id
    )
    await session.execute(
        text(
            "UPDATE identity.session SET revoked_at = now() "
            "WHERE id = :id AND revoked_at IS NULL"
        ),
        {"id": row.session_id},
    )


async def delete_account(
    session: AsyncSession,
    *,
    identity: Identity,
    http: httpx.AsyncClient,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    
    row = (await session.execute(
        text("SELECT supabase_user_id FROM identity.principal WHERE id = :pid"),
        {"pid": identity.principal_id}
    )).first()
    
    if row and row.supabase_user_id and cfg.supabase_service_role_key:
        await supabase_auth.delete_user(http, user_id=row.supabase_user_id, settings=cfg)
        
    await apply_rls_context(
        session, account_id=identity.account_id, principal_id=identity.principal_id
    )
    await session.execute(
        text("UPDATE identity.principal SET status = 'DELETED' WHERE id = :pid"),
        {"pid": identity.principal_id}
    )
    await session.execute(
        text("UPDATE identity.account SET status = 'DELETED' WHERE id = :aid"),
        {"aid": identity.account_id}
    )
    await session.execute(
        text(
            "UPDATE identity.session SET revoked_at = now() "
            "WHERE principal_id = :pid AND revoked_at IS NULL"
        ),
        {"pid": identity.principal_id}
    )
