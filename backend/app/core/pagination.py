"""One opaque-cursor codec, reused by every list endpoint — API-001 mandates
cursor pagination as the default for changing collections (offset/page-
number pagination on a frequently-changing timeline is an explicit
anti-pattern), and this exists so that convention is consistent by
construction rather than re-decided per endpoint.
"""

import base64
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    next_cursor: str | None
    has_more: bool


class InvalidCursorError(ValueError):
    """A client-supplied cursor didn't decode — API-001's VALIDATION_ERROR
    territory, not a 500."""


def encode_cursor(last_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(str(last_id).encode()).decode()


def decode_cursor(cursor: str) -> uuid.UUID:
    try:
        return uuid.UUID(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception as exc:
        raise InvalidCursorError(f"invalid cursor: {cursor!r}") from exc


async def paginate_by_id[T](
    session: AsyncSession,
    stmt: Select[tuple[T]],
    id_column: InstrumentedAttribute[uuid.UUID],
    *,
    cursor: str | None,
    limit: int,
    get_id: Callable[[T], uuid.UUID],
) -> Page[T]:
    """Keyset pagination on a UUIDv7 primary key. UUIDv7 is time-ordered by
    construction, so ordering by the raw id column already IS chronological
    order — no separate timestamp needs encoding into the cursor.

    `get_id` is an explicit extractor (usually `lambda row: row.id`) rather
    than an assumed `.id` attribute via a Protocol-bound TypeVar — mypy
    can't satisfy a bound-TypeVar Protocol check against SQLAlchemy
    declarative classes reliably (reproduced independently of PEP 695 vs
    classic Generic/TypeVar syntax), so this sidesteps that rather than
    fighting it with type: ignore comments.
    """
    if cursor is not None:
        stmt = stmt.where(id_column > decode_cursor(cursor))

    stmt = stmt.order_by(id_column).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())

    has_more = len(rows) > limit
    page_items = rows[:limit]
    next_cursor = encode_cursor(get_id(page_items[-1])) if has_more and page_items else None
    return Page(items=page_items, next_cursor=next_cursor, has_more=has_more)
