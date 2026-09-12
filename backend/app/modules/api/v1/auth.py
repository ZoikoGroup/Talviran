"""Authentication endpoints (API-001 shape, SEC-001 rules).

Four routes: sign up, sign in, sign out, and "who am I". The session lives in
a Secure/HttpOnly cookie, never in a body or a header the page can read, per
SEC-001 §8.1 and the §41 prohibition on localStorage session material.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import ErrorCode, TalvrinAPIError
from app.core.redis_client import get_redis
from app.modules.identity import rate_limit, service
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
) -> PrincipalOut:
    try:
        login = await service.register(db, email=body.email, password=body.password)
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
            db, email=body.email, password=body.password
        )
    except service.InvalidCredentials as exc:
        await db.rollback()
        raise TalvrinAPIError(
            code=ErrorCode.UNAUTHENTICATED,
            message="Incorrect email or password.",
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
