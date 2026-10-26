import uuid

from fastapi import APIRouter, HTTPException, status

from app.modules.api.v1.deps import IdentityDep, SessionDep
from app.modules.research import watchlist_service
from app.modules.research.watchlist_schemas import (
    WatchlistCreateIn,
    WatchlistItemIn,
    WatchlistItemOut,
    WatchlistOut,
    WatchlistUpdateIn,
)

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.get("", response_model=list[WatchlistOut])
async def list_watchlists(
    session: SessionDep,
    identity: IdentityDep,
) -> list[WatchlistOut]:
    items = await watchlist_service.list_watchlists(
        session,
        account_id=identity.account_id,
        principal_id=identity.principal_id,
    )
    return [WatchlistOut.model_validate(row) for row in items]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=WatchlistOut)
async def create_watchlist(
    body: WatchlistCreateIn,
    session: SessionDep,
    identity: IdentityDep,
) -> WatchlistOut:
    from app.modules.commercial.service import QuotaExceededError, enforce_quota_limit

    try:
        await enforce_quota_limit(session, account_id=identity.account_id, quota_key="watchlists")
    except QuotaExceededError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    created = await watchlist_service.create_watchlist(
        session,
        account_id=identity.account_id,
        principal_id=identity.principal_id,
        data=body,
    )
    return WatchlistOut.model_validate(created)


@router.get("/{watchlist_id}", response_model=WatchlistOut)
async def get_watchlist(
    watchlist_id: uuid.UUID,
    session: SessionDep,
    identity: IdentityDep,
) -> WatchlistOut:
    wl = await watchlist_service.get_watchlist(
        session,
        watchlist_id=watchlist_id,
        account_id=identity.account_id,
    )
    if wl is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return WatchlistOut.model_validate(wl)


@router.patch("/{watchlist_id}", response_model=WatchlistOut)
async def update_watchlist(
    watchlist_id: uuid.UUID,
    body: WatchlistUpdateIn,
    session: SessionDep,
    identity: IdentityDep,
) -> WatchlistOut:
    updated = await watchlist_service.update_watchlist(
        session,
        watchlist_id=watchlist_id,
        account_id=identity.account_id,
        data=body,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return WatchlistOut.model_validate(updated)


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: uuid.UUID,
    session: SessionDep,
    identity: IdentityDep,
) -> None:
    ok = await watchlist_service.delete_watchlist(
        session,
        watchlist_id=watchlist_id,
        account_id=identity.account_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist not found")


@router.post(
    "/{watchlist_id}/items",
    status_code=status.HTTP_201_CREATED,
    response_model=WatchlistItemOut,
)
async def add_item(
    watchlist_id: uuid.UUID,
    body: WatchlistItemIn,
    session: SessionDep,
    identity: IdentityDep,
) -> WatchlistItemOut:
    try:
        item = await watchlist_service.add_watchlist_item(
            session,
            watchlist_id=watchlist_id,
            account_id=identity.account_id,
            item_in=body,
        )
        return WatchlistItemOut.model_validate(item)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{watchlist_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(
    watchlist_id: uuid.UUID,
    item_id: uuid.UUID,
    session: SessionDep,
    identity: IdentityDep,
) -> None:
    ok = await watchlist_service.remove_watchlist_item(
        session,
        watchlist_id=watchlist_id,
        item_id=item_id,
        account_id=identity.account_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
