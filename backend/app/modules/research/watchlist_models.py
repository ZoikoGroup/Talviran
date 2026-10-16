import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class Watchlist(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "watchlist"
    __table_args__ = {"schema": "research"}

    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.account.id", ondelete="CASCADE"), index=True
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.principal.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    items: Mapped[list["WatchlistItem"]] = relationship(
        "WatchlistItem",
        back_populates="watchlist",
        cascade="all, delete-orphan",
        order_by="WatchlistItem.sort_order",
    )


class WatchlistItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "watchlist_item"
    __table_args__ = {"schema": "research"}

    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.account.id", ondelete="CASCADE"), index=True
    )
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research.watchlist.id", ondelete="CASCADE"), index=True
    )
    symbol: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    asset_class: Mapped[str] = mapped_column(String(32))
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("reference.instrument.id", ondelete="SET NULL"),
        default=None,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    watchlist: Mapped[Watchlist] = relationship("Watchlist", back_populates="items")
