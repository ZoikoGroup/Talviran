import datetime as dt
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WatchlistItemIn(BaseModel):
    symbol: str = Field(..., max_length=64)
    name: str = Field(..., max_length=200)
    asset_class: str = Field(..., max_length=32)
    instrument_id: UUID | None = None
    sort_order: int = 0


class WatchlistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    watchlist_id: UUID
    symbol: str
    name: str
    asset_class: str
    instrument_id: UUID | None = None
    sort_order: int
    created_at: dt.datetime


class WatchlistCreateIn(BaseModel):
    name: str = Field(..., max_length=120)
    description: str | None = Field(default=None, max_length=500)
    is_default: bool = False
    items: list[WatchlistItemIn] = Field(default_factory=list)


class WatchlistUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    is_default: bool | None = None


class WatchlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    is_default: bool
    created_at: dt.datetime
    updated_at: dt.datetime
    items: list[WatchlistItemOut] = Field(default_factory=list)
