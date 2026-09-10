import datetime as dt
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import get_settings
from app.core.uuid7 import new_uuid7


class Base(DeclarativeBase):
    """Shared declarative base. Every module's models.py imports this — it does
    not imply shared schema ownership; each model sets its own `__table_args__
    = {"schema": "..."}`.

    type_annotation_map makes every bare `Mapped[dt.datetime]` timezone-aware
    (timestamptz) by default — Talvrin has no naive-datetime columns anywhere
    (bitemporal ranges, freshness SLOs, etc. all depend on tz-aware values),
    so this is safer as a blanket default than trusting every model author to
    remember `DateTime(timezone=True)` on every column.
    """

    type_annotation_map = {dt.datetime: DateTime(timezone=True)}


class UUIDPrimaryKeyMixin:
    """Opaque, time-ordered UUIDv7 primary key (DATA-001) — every table uses
    this instead of a bare Integer or uuid4() so IDs never leak sequence
    information and stay index-friendly.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid7
    )


class CreatedAtMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Per-request session; callers commit explicitly."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
