"""Authentication endpoints (API-001 shape, SEC-001 rules).

Four routes: sign up, sign in, sign out, and "who am I". The session lives in
a Secure/HttpOnly cookie, never in a body or a header the page can read, per
SEC-001 §8.1 and the §41 prohibition on localStorage session material.
"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import ErrorCode, TalvrinAPIError
from app.core.http_client import get_http_client
from app.core.redis_client import get_redis
from app.modules.identity import rate_limit, reset_tokens, service
from app.modules.identity.cookies import (
    SESSION_COOKIE_NAME,
    CookiePolicy,
    clear_session_cookie,
    set_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _redis() -> Redis:
    return get_redis()


RedisDep = Annotated[Redis, Depends(_redis)]


def _http() -> httpx.AsyncClient:
    return get_http_client()


HttpDep = Annotated[httpx.AsyncClient, Depends(_http)]


def _cookie_policy() -> CookiePolicy:
    return CookiePolicy.for_environment(get_settings().environment)


def _client_ip(request: Request) -> str:
    """Best-effort client address.

    Behind a proxy the socket address is the proxy, so the first hop in
    X-Forwarded-For is used when present. That header is caller-controlled and
    therefore spoofable — it is good enough to bucket honest traffic, and the
    per-identifier limit is what actually resists a determined attacker.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class Credentials(BaseModel):
    email: EmailStr
    # Bounded so an oversized body cannot turn Argon2's per-hash cost into a
    # CPU exhaustion vector before the policy check runs.
    password: str = Field(min_length=1, max_length=4096)


class PrincipalOut(BaseModel):
    principal_id: str
    account_id: str
    email: str


def _principal_out(identity: service.Identity) -> PrincipalOut:
    return PrincipalOut(
        principal_id=str(identity.principal_id),
        account_id=str(identity.account_id),
        email=identity.email,
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    body: Credentials,
    response: Response,
    db: SessionDep,
    http: HttpDep,
) -> PrincipalOut:
    try:
        login = await service.register(
            db, email=body.email, password=body.password, http=http
        )
    except service.WeakPassword as exc:
        raise TalvrinAPIError(
            code=ErrorCode.VALIDATION_ERROR, message=exc.reason
        ) from exc
    except service.EmailAlreadyRegistered as exc:
        # Sign-up cannot avoid revealing that an address is taken — the user
        # has to be told why it failed. Sign-in still gives nothing away.
        raise TalvrinAPIError(
            code=ErrorCode.CONFLICT,
            message="An account already exists for that email address.",
        ) from exc

    await db.commit()
    set_session_cookie(
        response,
        token=login.token,
        expires_at=login.absolute_expiry,
        policy=_cookie_policy(),
    )
    return _principal_out(login.identity)


@router.post("/login")
async def login(
    body: Credentials,
    request: Request,
    response: Response,
    db: SessionDep,
    redis: RedisDep,
    http: HttpDep,
) -> PrincipalOut:
    ip = _client_ip(request)
    decision = await rate_limit.check_and_count(
        redis, identifier=body.email, client_ip=ip
    )
    if not decision.allowed:
        raise TalvrinAPIError(
            code=ErrorCode.RATE_LIMITED,
            message="Too many sign-in attempts. Please try again later.",
            retry_after_seconds=decision.retry_after_seconds,
        )

    try:
        issued = await service.authenticate(
            db, email=body.email, password=body.password, http=http
        )
    except service.InvalidCredentials as exc:
        await db.rollback()
        raise TalvrinAPIError(
            code=ErrorCode.UNAUTHENTICATED,
            message="Incorrect email or password.",
        ) from exc
    except service.EmailNotConfirmed as exc:
        await db.rollback()
        raise TalvrinAPIError(
            code=ErrorCode.UNAUTHENTICATED,
            message="Please confirm your email address before signing in.",
        ) from exc

    await db.commit()
    await rate_limit.clear(redis, identifier=body.email, client_ip=ip)
    set_session_cookie(
        response,
        token=issued.token,
        expires_at=issued.absolute_expiry,
        policy=_cookie_policy(),
    )
    return _principal_out(issued.identity)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: SessionDep) -> None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await service.revoke_session(db, token=token)
        await db.commit()
    # The cookie is cleared either way: a caller holding a stale token should
    # still end up signed out rather than stuck.
    clear_session_cookie(response, policy=_cookie_policy())


class ForgotPasswordIn(BaseModel):
    email: EmailStr


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(body: ForgotPasswordIn, http: HttpDep) -> None:
    """Always 202, whether or not the address has an account.

    Matching /login's enumeration resistance (SEC-001 §7.1): Supabase's own
    `/auth/v1/recover` already answers identically for a known and an
    unknown address, so there is nothing here to branch on that wouldn't
    reopen the thing that endpoint already closed.
    """
    settings = get_settings()
    await service.request_password_reset(
        email=body.email,
        http=http,
        settings=settings,
        redirect_to=f"{settings.frontend_url}/reset-password",
    )


class ResetPasswordIn(BaseModel):
    #: The `access_token` from the recovery link's `#access_token=...`
    #: fragment — see identity.service.complete_password_reset.
    access_token: str = Field(min_length=1)
    new_password: str = Field(min_length=1, max_length=4096)


_EXPIRED_LINK_MESSAGE = "This reset link is invalid or has expired. Request a new one."


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordIn,
    response: Response,
    db: SessionDep,
    http: HttpDep,
    redis: RedisDep,
) -> PrincipalOut:
    # Checked before Supabase is even called: Supabase's own token stays
    # valid for its full lifetime and would happily accept a second call —
    # see identity/reset_tokens.py for why this app enforces single-use
    # itself rather than relying on that.
    if await reset_tokens.is_spent(redis, access_token=body.access_token):
        raise TalvrinAPIError(
            code=ErrorCode.UNAUTHENTICATED, message=_EXPIRED_LINK_MESSAGE
        )

    try:
        issued = await service.complete_password_reset(
            db, access_token=body.access_token, new_password=body.new_password, http=http
        )
    except service.InvalidResetToken as exc:
        await db.rollback()
        raise TalvrinAPIError(
            code=ErrorCode.UNAUTHENTICATED, message=_EXPIRED_LINK_MESSAGE
        ) from exc
    except service.WeakPassword as exc:
        await db.rollback()
        raise TalvrinAPIError(
            code=ErrorCode.VALIDATION_ERROR, message=exc.reason
        ) from exc

    await db.commit()
    # Marked spent only now that the password has actually changed — a
    # request rejected for a weak password leaves the link usable for a
    # retry rather than burning it on a mistake.
    await reset_tokens.mark_spent(redis, access_token=body.access_token)
    set_session_cookie(
        response,
        token=issued.token,
        expires_at=issued.absolute_expiry,
        policy=_cookie_policy(),
    )
    return _principal_out(issued.identity)


@router.get("/me")
async def me(request: Request, db: SessionDep) -> PrincipalOut:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    identity = (
        await service.resolve_session(db, token=token) if token else None
    )
    if identity is None:
        raise TalvrinAPIError(
            code=ErrorCode.UNAUTHENTICATED, message="Not signed in."
        )
    await db.commit()
    return _principal_out(identity)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(request: Request, response: Response, db: SessionDep, http: HttpDep) -> None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    identity = (
        await service.resolve_session(db, token=token) if token else None
    )
    if identity is None:
        raise TalvrinAPIError(
            code=ErrorCode.UNAUTHENTICATED, message="Not signed in."
        )
    await service.delete_account(db, identity=identity, http=http)
    await db.commit()
    clear_session_cookie(response, policy=_cookie_policy())

