"""Supabase Auth (GoTrue) — the credential and session engine.

Replaces the Argon2id password column and hand-rolled verification that used
to live here. Everything about *how* a password is stored, hashed and
checked, and how a password-reset email actually gets sent, is now Supabase's
problem, not ours — this module is a thin, typed wrapper around the three
GoTrue REST endpoints the rest of the identity module calls.

Deliberately plain `httpx` rather than the `supabase-py` SDK: the SDK pulls
in its own sync/async client management and a surface far wider than three
endpoints, and this codebase already has a house style for thin HTTP wrappers
that take a caller-supplied `httpx.AsyncClient` (see
`market/connectors/dmo_gilts/client.py`) — that same shape is what lets tests
substitute a fake transport instead of hitting the network, exactly as they
already do for the database and Redis.

The response shapes and error codes below are not guessed — most were
confirmed against the real project this codebase is configured against
(2026-09-16): `/token` distinguishes `invalid_credentials` from
`email_not_confirmed`; `/recover` returns `200 {}` for both a known and an
unknown address, which is exactly the enumeration resistance SEC-001 §7.1
already required of the login endpoint. One shape was only observed with
email confirmation switched on — `/signup` returned the user object at the
*top level*, no session — and GoTrue is documented to instead nest it under
`user` (alongside a `session`) when confirmation is off, the mode this
product actually runs in. `sign_up` below accepts either shape rather than
assuming the one that happened to be observable at the time.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx

from app.core.config import Settings


class SupabaseAuthError(Exception):
    """Base for a GoTrue call that failed in a way the caller must handle."""


class EmailAlreadyRegistered(SupabaseAuthError):
    """Raised on sign-up only. Supabase itself is the source of truth for
    email uniqueness now, so this is discovered by asking it, not by an
    index we own."""


class WeakPassword(SupabaseAuthError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidCredentials(SupabaseAuthError):
    """Deliberately covers both a wrong password and an unknown address —
    Supabase's own `invalid_credentials` error code already collapses the
    two, which is the enumeration-resistance property §7.1 asks for."""


class EmailNotConfirmed(SupabaseAuthError):
    """Distinct from InvalidCredentials on purpose: Supabase's own API
    already exposes this as a separate, named error code, so folding it into
    a generic failure would be a regression in honesty, not a security gain.
    Only reachable if email confirmation is enabled on the project — this
    codebase runs with it disabled so sign-up can sign a user in immediately,
    matching the product's existing sign-up UX."""


class SupabaseUnavailable(SupabaseAuthError):
    """GoTrue returned something outside the shapes this module knows how to
    interpret, or the request failed outright. Never silently reinterpreted
    as invalid credentials — that would turn an outage into every user
    looking like they mistyped their password."""


@dataclass(frozen=True)
class SupabaseUser:
    id: uuid.UUID
    email: str


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "apikey": settings.supabase_anon_key,
        "Content-Type": "application/json",
    }


def _error_fields(body: object) -> tuple[str, str]:
    """(error_code, message), tolerant of GoTrue's inconsistent error shapes
    across endpoints and versions (`error_code`/`code`, `msg`/`message`/
    `error_description`)."""
    if not isinstance(body, dict):
        return "", ""
    code = str(body.get("error_code") or body.get("code") or "")
    message = str(
        body.get("msg") or body.get("message") or body.get("error_description") or ""
    )
    return code, message


async def sign_up(
    client: httpx.AsyncClient, *, email: str, password: str, settings: Settings
) -> SupabaseUser:
    """Creates the account in Supabase. Raises EmailAlreadyRegistered or
    WeakPassword for the cases the caller can explain to the user."""
    try:
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/signup",
            json={"email": email, "password": password},
            headers=_headers(settings),
        )
    except httpx.HTTPError as exc:
        raise SupabaseUnavailable(f"sign-up request failed: {exc}") from exc

    body = resp.json() if resp.content else {}

    if resp.status_code >= 400:
        code, message = _error_fields(body)
        lowered = message.lower()
        if code in ("user_already_exists", "email_exists") or "already registered" in lowered:
            raise EmailAlreadyRegistered(email)
        if code == "weak_password" or (
            "password" in lowered and any(w in lowered for w in ("weak", "short", "at least"))
        ):
            raise WeakPassword(message or "Password does not meet requirements.")
        raise SupabaseUnavailable(f"sign-up failed ({resp.status_code}): {message or body}")

    # A duplicate sign-up against an address that already has a confirmed
    # identity comes back 200 (not 4xx) with no new identity created — the
    # empty `identities` array is GoTrue's documented signal for that case,
    # distinct from a first-time sign-up which populates it. Only present at
    # the top level, so this check must happen before unwrapping `user`.
    if body.get("identities") == []:
        raise EmailAlreadyRegistered(email)

    # With email confirmation on, the user's own fields sit at the top
    # level and there is no session yet. With it off (this product's mode),
    # GoTrue instead nests them under "user" alongside an immediate
    # "session" — accept either rather than assume the one observed.
    nested = body.get("user")
    user: dict[str, object] = nested if isinstance(nested, dict) else body
    if "id" not in user or "email" not in user:
        raise SupabaseUnavailable(f"sign-up returned an unrecognised body: {body}")
    return SupabaseUser(id=uuid.UUID(str(user["id"])), email=str(user["email"]))


async def sign_in_with_password(
    client: httpx.AsyncClient, *, email: str, password: str, settings: Settings
) -> SupabaseUser:
    """Verifies credentials. Raises InvalidCredentials or EmailNotConfirmed —
    never returns a user for anything short of a genuine match."""
    try:
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/token",
            params={"grant_type": "password"},
            json={"email": email, "password": password},
            headers=_headers(settings),
        )
    except httpx.HTTPError as exc:
        raise SupabaseUnavailable(f"sign-in request failed: {exc}") from exc

    body = resp.json() if resp.content else {}

    if resp.status_code >= 400:
        code, _ = _error_fields(body)
        if code == "email_not_confirmed":
            raise EmailNotConfirmed
        # invalid_grant / invalid_credentials / anything else the API might
        # start returning for a rejected login: still a rejected login.
        raise InvalidCredentials

    user = body.get("user")
    if not isinstance(user, dict) or "id" not in user or "email" not in user:
        raise SupabaseUnavailable(f"sign-in returned an unrecognised body: {body}")
    return SupabaseUser(id=uuid.UUID(user["id"]), email=user["email"])


class InvalidResetToken(SupabaseAuthError):
    """The recovery access token was missing, malformed, expired, or already
    used. Confirmed live (2026-09-16): a malformed bearer on `/auth/v1/user`
    comes back `403 bad_jwt`; GoTrue is not documented to use one single code
    for every way a recovery token can be bad, so this treats any 4xx here
    as this rather than pattern-matching a specific message."""


async def update_password(
    client: httpx.AsyncClient, *, access_token: str, new_password: str, settings: Settings
) -> SupabaseUser:
    """Sets a new password using the access token from a Supabase recovery
    link — the `#access_token=...&type=recovery` fragment GoTrue's
    `/auth/v1/verify` redirect leaves on the frontend's reset-password page.

    This is the one call in this module that authenticates as the *user*
    (via their own bearer token) rather than as the anon client — matching
    exactly what clicking the email link entitles them to do: prove they
    control that token, and nothing else.
    """
    try:
        resp = await client.put(
            f"{settings.supabase_url}/auth/v1/user",
            json={"password": new_password},
            headers={
                "apikey": settings.supabase_anon_key,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        raise SupabaseUnavailable(f"password update request failed: {exc}") from exc

    body = resp.json() if resp.content else {}

    if resp.status_code >= 400:
        code, message = _error_fields(body)
        if code == "weak_password" or (
            "password" in message.lower()
            and any(w in message.lower() for w in ("weak", "short", "at least"))
        ):
            raise WeakPassword(message or "Password does not meet requirements.")
        raise InvalidResetToken

    if "id" not in body or "email" not in body:
        raise SupabaseUnavailable(f"password update returned an unrecognised body: {body}")
    return SupabaseUser(id=uuid.UUID(body["id"]), email=body["email"])


async def request_password_reset(
    client: httpx.AsyncClient,
    *,
    email: str,
    settings: Settings,
    redirect_to: str | None = None,
) -> None:
    """Asks Supabase to send a reset email. Deliberately returns nothing and
    raises nothing for "the address doesn't exist" — GoTrue itself answers
    200 either way, which is the enumeration resistance the caller wants; a
    transport failure still raises, since that is an operational problem the
    caller should know about rather than silently swallow."""
    payload: dict[str, str] = {"email": email}
    if redirect_to:
        payload["redirect_to"] = redirect_to
    try:
        await client.post(
            f"{settings.supabase_url}/auth/v1/recover",
            json=payload,
            headers=_headers(settings),
        )
    except httpx.HTTPError as exc:
        raise SupabaseUnavailable(f"password reset request failed: {exc}") from exc


async def delete_user(
    client: httpx.AsyncClient, *, user_id: uuid.UUID, settings: Settings
) -> None:
    """Deletes a user from Supabase GoTrue via the admin API."""
    if not settings.supabase_service_role_key:
        return
    try:
        resp = await client.delete(
            f"{settings.supabase_url}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        raise SupabaseUnavailable(f"delete user request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise SupabaseUnavailable(f"delete user failed ({resp.status_code})")
