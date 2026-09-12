"""Authentication service (SEC-001 §5–§9).

Everything here is deliberately shaped around three rules from the spec:

1. **No account enumeration** (§7.1). Sign-in returns the same failure whether
   the email is unknown, the password is wrong, or the principal is suspended.
   To keep the *timing* the same too, a miss still performs one Argon2 verify
   against a dummy hash — otherwise "fast rejection" tells an attacker the
   address is unregistered just as loudly as a different error message would.

2. **Sessions are server-side rows** (§8), not self-contained signed tokens,
   because revocation has to be immediate and absolute. The cookie carries a
   random token; only its digest is stored.

3. **RLS is never bypassed wholesale.** Reads that must happen before an
   identity exists go through the two narrow SECURITY DEFINER functions from
   migration 0009. Everything after that runs with `app.account_id` and
   `app.principal_id` set, so ordinary policies apply.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uuid7 import new_uuid7
from app.modules.identity import tokens
from app.modules.identity.passwords import (
    BreachScreen,
    NullBreachScreen,
    PasswordPolicyError,
    check_policy,
    hash_password,
    verify_password,
)

#: A real Argon2id hash of a value no one can present. Verifying against this
#: on a failed lookup keeps the timing of "unknown email" and "wrong password"
#: indistinguishable. Generated once at import, not per call.
_DUMMY_HASH = hash_password(str(uuid.uuid4()) + "-unmatchable")


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


async def register(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    breach_screen: BreachScreen | None = None,
) -> IssuedLogin:
    """Creates an account, its first principal, and a signed-in session."""
    address = normalise_email(email)

    try:
        check_policy(password)
    except PasswordPolicyError as exc:
        raise WeakPassword(str(exc)) from exc

    screen = breach_screen or NullBreachScreen()
    if await screen.is_compromised(password):
        raise WeakPassword(
            "That password has appeared in a known data breach. Please choose another."
        )

    existing = (
        await session.execute(
            text("SELECT principal_id FROM identity.lookup_principal_for_auth(:e)"),
            {"e": address},
        )
    ).first()
    if existing is not None:
        raise EmailAlreadyRegistered(address)

    account_id = new_uuid7()
    principal_id = new_uuid7()

    # identity.account has no RLS; principal does, so the context has to be in
    # place before the insert or its WITH CHECK rejects our own row.
    await session.execute(
        text(
            "INSERT INTO identity.account (id, name, status) "
            "VALUES (:id, :name, 'ACTIVE')"
        ),
        {"id": account_id, "name": address},
    )
    await apply_rls_context(session, account_id=account_id, principal_id=principal_id)
    await session.execute(
        text(
            "INSERT INTO identity.principal "
            "(id, account_id, email, status, password_hash) "
            "VALUES (:id, :account_id, :email, 'ACTIVE', :hash)"
        ),
        {
            "id": principal_id,
            "account_id": account_id,
            "email": address,
            "hash": hash_password(password),
        },
    )

    identity = Identity(principal_id=principal_id, account_id=account_id, email=address)
    return await _issue_session(session, identity)


async def authenticate(
    session: AsyncSession, *, email: str, password: str
) -> IssuedLogin:
    """Verifies credentials and starts a session.

    Raises InvalidCredentials for every failure mode, by design.
    """
    address = normalise_email(email)
    row = (
        await session.execute(
            text(
                "SELECT principal_id, account_id, email, status, password_hash "
                "FROM identity.lookup_principal_for_auth(:e)"
            ),
            {"e": address},
        )
    ).first()

    # Unknown address, or a principal with no password (passkey-only, or not
    # yet set): still spend the time, then fail identically.
    if row is None or row.password_hash is None:
        verify_password(_DUMMY_HASH, password)
        raise InvalidCredentials

    result = verify_password(row.password_hash, password)
    if not result.ok:
        raise InvalidCredentials

    # Status is checked *after* the password so a suspended account cannot be
    # distinguished from a wrong password by an attacker probing addresses.
    if row.status != "ACTIVE":
        raise InvalidCredentials

    identity = Identity(
        principal_id=row.principal_id, account_id=row.account_id, email=row.email
    )
    await apply_rls_context(
        session, account_id=identity.account_id, principal_id=identity.principal_id
    )

    # §7: a login is the only moment the plaintext exists, so it is the only
    # chance to re-hash one stored under weaker parameters.
    if result.needs_rehash:
        await session.execute(
            text(
                "UPDATE identity.principal SET password_hash = :h WHERE id = :id"
            ),
            {"h": hash_password(password), "id": identity.principal_id},
        )

    return await _issue_session(session, identity)


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
