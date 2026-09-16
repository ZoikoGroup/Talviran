"""Request dependencies shared by the authenticated v1 endpoints.

`current_identity` is the only place a request acquires an account. Resolving
the session also applies the RLS context to the request's database session, so
everything downstream is scoped by the database as well as by the code —
SEC-001 §11's two boundaries, obtained without every handler remembering to
ask for them.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import ErrorCode, TalvrinAPIError
from app.core.redis_client import get_redis
from app.modules.identity import service as identity_service
from app.modules.identity.cookies import SESSION_COOKIE_NAME
from app.modules.research import service as research_service
from app.modules.research.crypto import KeyWrapper
from app.modules.research.keys import get_key_wrapper

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]


async def current_identity(
    request: Request, db: SessionDep
) -> identity_service.Identity:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    identity = (
        await identity_service.resolve_session(db, token=token) if token else None
    )
    if identity is None:
        raise TalvrinAPIError(
            code=ErrorCode.UNAUTHENTICATED, message="Not signed in."
        )
    return identity


IdentityDep = Annotated[identity_service.Identity, Depends(current_identity)]


def key_wrapper() -> KeyWrapper:
    return get_key_wrapper()


WrapperDep = Annotated[KeyWrapper, Depends(key_wrapper)]


async def account_dek(
    db: SessionDep, identity: IdentityDep, wrapper: WrapperDep
) -> bytes:
    """The request's content key.

    Resolved once per request rather than per row: in production unwrapping is
    a KMS round trip, and FastAPI caches a dependency's result within a
    request, so handlers can depend on this freely.
    """
    return await research_service.account_dek(
        db, account_id=identity.account_id, wrapper=wrapper
    )


DekDep = Annotated[bytes, Depends(account_dek)]
