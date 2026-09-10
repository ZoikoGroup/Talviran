"""Direct tests of app.core.pagination against real reference.issuer rows —
isolates pagination correctness from the PDP/rights gating already covered
in test_reference_api.py.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import paginate_by_id
from app.modules.reference.models import Issuer


async def _seed_issuers(session: AsyncSession, n: int) -> list[uuid.UUID]:
    issuers = [Issuer(name=f"Issuer {i}", status="ACTIVE") for i in range(n)]
    session.add_all(issuers)
    await session.flush()
    await session.commit()
    return [issuer.id for issuer in issuers]


async def test_pagination_returns_all_items_in_id_order_across_pages(
    db_session: AsyncSession,
) -> None:
    inserted_ids = await _seed_issuers(db_session, 5)

    seen: list[uuid.UUID] = []
    cursor: str | None = None
    for _ in range(10):  # safety bound against an infinite loop on a logic bug
        page = await paginate_by_id(
            db_session,
            select(Issuer),
            Issuer.id,
            cursor=cursor,
            limit=2,
            get_id=lambda row: row.id,
        )
        seen.extend(item.id for item in page.items)
        if not page.has_more:
            break
        cursor = page.next_cursor

    # UUIDv7 is time-ordered and we inserted in order, so insertion order
    # (inserted_ids) must exactly match pagination order (seen).
    assert seen == inserted_ids


async def test_empty_table_returns_empty_page(db_session: AsyncSession) -> None:
    page = await paginate_by_id(
        db_session, select(Issuer), Issuer.id, cursor=None, limit=10, get_id=lambda row: row.id
    )
    assert page.items == []
    assert page.next_cursor is None
    assert page.has_more is False


async def test_exact_page_boundary_has_no_next_cursor(db_session: AsyncSession) -> None:
    """5 items with limit=5 should NOT report has_more — this is the classic
    off-by-one an internal `limit()` (not `limit + 1`) would get wrong.
    """
    await _seed_issuers(db_session, 5)

    page = await paginate_by_id(
        db_session, select(Issuer), Issuer.id, cursor=None, limit=5, get_id=lambda row: row.id
    )
    assert len(page.items) == 5
    assert page.has_more is False
    assert page.next_cursor is None
