import uuid
from collections.abc import Sequence
from typing import Any, TypedDict, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.uuid7 import new_uuid7
from app.modules.research.watchlist_models import Watchlist, WatchlistItem
from app.modules.research.watchlist_schemas import (
    WatchlistCreateIn,
    WatchlistItemIn,
    WatchlistUpdateIn,
)


class PresetItem(TypedDict):
    symbol: str
    name: str
    asset_class: str


class PresetWatchlist(TypedDict):
    name: str
    description: str
    is_default: bool
    items: list[PresetItem]


DEFAULT_PRESETS: list[PresetWatchlist] = [
    {
        "name": "Global Sovereign 10Y",
        "description": "Key sovereign benchmark 10-year yields and benchmark debt",
        "is_default": True,
        "items": [
            {
                "symbol": "UK 10Y Gilt",
                "name": "UK 10-Year Benchmark Gilt",
                "asset_class": "RATES",
            },
            {
                "symbol": "US 10Y Treasury",
                "name": "US 10-Year Treasury Note",
                "asset_class": "RATES",
            },
            {
                "symbol": "DE 10Y Bund",
                "name": "Germany 10-Year Bund",
                "asset_class": "RATES",
            },
            {
                "symbol": "JP 10Y JGB",
                "name": "Japan 10-Year JGB",
                "asset_class": "RATES",
            },
        ],
    },
    {
        "name": "Major Indices & FX",
        "description": "Primary equity indices and currency pairs",
        "is_default": False,
        "items": [
            {"symbol": "S&P 500", "name": "S&P 500 Index", "asset_class": "EQUITY"},
            {"symbol": "FTSE 100", "name": "FTSE 100 Index", "asset_class": "EQUITY"},
            {"symbol": "GBP/USD", "name": "British Pound / US Dollar", "asset_class": "FX"},
            {"symbol": "EUR/USD", "name": "Euro / US Dollar", "asset_class": "FX"},
        ],
    },
]


async def ensure_default_watchlists(
    session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID
) -> None:
    """Creates initial default watchlists for a newly signed-in user if none exist."""
    existing = await session.execute(
        select(Watchlist.id).where(Watchlist.account_id == account_id).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        return

    for preset in DEFAULT_PRESETS:
        wl_id = new_uuid7()
        wl = Watchlist(
            id=wl_id,
            account_id=account_id,
            principal_id=principal_id,
            name=preset["name"],
            description=preset["description"],
            is_default=preset["is_default"],
        )
        session.add(wl)
        for idx, item in enumerate(preset["items"]):
            item_obj = WatchlistItem(
                id=new_uuid7(),
                account_id=account_id,
                watchlist_id=wl_id,
                symbol=item["symbol"],
                name=item["name"],
                asset_class=item["asset_class"],
                sort_order=idx,
            )
            session.add(item_obj)
    await session.commit()


async def list_watchlists(
    session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID
) -> Sequence[Watchlist]:
    await ensure_default_watchlists(session, account_id=account_id, principal_id=principal_id)
    stmt = (
        select(Watchlist)
        .where(Watchlist.account_id == account_id)
        .options(selectinload(Watchlist.items))
        .order_by(Watchlist.created_at.asc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_watchlist(
    session: AsyncSession, *, watchlist_id: uuid.UUID, account_id: uuid.UUID
) -> Watchlist | None:
    stmt = (
        select(Watchlist)
        .where(Watchlist.id == watchlist_id, Watchlist.account_id == account_id)
        .options(selectinload(Watchlist.items))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_watchlist(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    principal_id: uuid.UUID,
    data: WatchlistCreateIn,
) -> Watchlist:
    wl_id = new_uuid7()
    wl = Watchlist(
        id=wl_id,
        account_id=account_id,
        principal_id=principal_id,
        name=data.name,
        description=data.description,
        is_default=data.is_default,
    )
    session.add(wl)
    for idx, item in enumerate(data.items):
        item_obj = WatchlistItem(
            id=new_uuid7(),
            account_id=account_id,
            watchlist_id=wl_id,
            symbol=item.symbol,
            name=item.name,
            asset_class=item.asset_class,
            instrument_id=item.instrument_id,
            sort_order=item.sort_order or idx,
        )
        session.add(item_obj)
    await session.commit()
    res = await get_watchlist(session, watchlist_id=wl_id, account_id=account_id)
    assert res is not None
    return res


async def update_watchlist(
    session: AsyncSession,
    *,
    watchlist_id: uuid.UUID,
    account_id: uuid.UUID,
    data: WatchlistUpdateIn,
) -> Watchlist | None:
    wl = await get_watchlist(session, watchlist_id=watchlist_id, account_id=account_id)
    if wl is None:
        return None
    if data.name is not None:
        wl.name = data.name
    if data.description is not None:
        wl.description = data.description
    if data.is_default is not None:
        wl.is_default = data.is_default
    await session.commit()
    return wl


async def delete_watchlist(
    session: AsyncSession, *, watchlist_id: uuid.UUID, account_id: uuid.UUID
) -> bool:
    wl = await get_watchlist(session, watchlist_id=watchlist_id, account_id=account_id)
    if wl is None:
        return False
    await session.delete(wl)
    await session.commit()
    return True


async def add_watchlist_item(
    session: AsyncSession,
    *,
    watchlist_id: uuid.UUID,
    account_id: uuid.UUID,
    item_in: WatchlistItemIn,
) -> WatchlistItem:
    wl = await get_watchlist(session, watchlist_id=watchlist_id, account_id=account_id)
    if wl is None:
        raise ValueError("Watchlist not found")
    item = WatchlistItem(
        id=new_uuid7(),
        account_id=account_id,
        watchlist_id=watchlist_id,
        symbol=item_in.symbol,
        name=item_in.name,
        asset_class=item_in.asset_class,
        instrument_id=item_in.instrument_id,
        sort_order=item_in.sort_order or len(wl.items),
    )
    session.add(item)
    await session.commit()
    return item


async def remove_watchlist_item(
    session: AsyncSession,
    *,
    watchlist_id: uuid.UUID,
    item_id: uuid.UUID,
    account_id: uuid.UUID,
) -> bool:
    stmt = delete(WatchlistItem).where(
        WatchlistItem.id == item_id,
        WatchlistItem.watchlist_id == watchlist_id,
        WatchlistItem.account_id == account_id,
    )
    result = await session.execute(stmt)
    await session.commit()
    cursor_res = cast("CursorResult[Any]", result)
    return bool(cursor_res.rowcount > 0)
