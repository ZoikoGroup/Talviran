"""identity schema — owned exclusively by this module (no other module writes
identity.*). Minimal P0 shape: full SEC-001 hardening (MFA, passkeys, SCIM,
step-up) is deferred to P2 — this is enough to have a real account_id/
principal_id for RLS to scope against everywhere else.
"""

import datetime as dt
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class Account(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "account"
    __table_args__ = {"schema": "identity"}

    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class Principal(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "principal"
    __table_args__ = {"schema": "identity"}

    account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.account.id"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class Session(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "session"
    __table_args__ = {"schema": "identity"}

    principal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.principal.id"), index=True
    )
    expires_at: Mapped[dt.datetime]
    revoked_at: Mapped[dt.datetime | None] = mapped_column(default=None)
