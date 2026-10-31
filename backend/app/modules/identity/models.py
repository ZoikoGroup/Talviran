import datetime as dt
import uuid

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class Account(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "account"
    __table_args__ = {"schema": "identity"}

    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    plan_tier: Mapped[str] = mapped_column(
        String(32), default="professional", server_default="professional"
    )
    billing_cadence: Mapped[str] = mapped_column(
        String(32), default="annual", server_default="annual"
    )
    seat_count: Mapped[int] = mapped_column(default=1, server_default="1")
    current_period_end: Mapped[dt.datetime | None] = mapped_column(default=None, nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(
        default=False, server_default=text("false"), nullable=False
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), default=None, nullable=True
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), default=None, nullable=True
    )


class Principal(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "principal"
    __table_args__ = {"schema": "identity"}

    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.account.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.user.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(32), default="owner")


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "user"
    __table_args__ = {"schema": "identity"}

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(200), default=None)
    totp_secret: Mapped[str | None] = mapped_column(String(255), default=None)
    totp_enabled: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
