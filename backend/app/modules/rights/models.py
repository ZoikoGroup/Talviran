"""governance schema (shared with app.modules.policy — see plan §0: `rights` +
`policy` both write to `governance`, mapping ENG-ARCH-003's 13 modules onto
DATA-001's 9 schemas). Not account-scoped — these are platform-wide
governance objects, so no RLS here (contrast identity.*).
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class RightsProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One rights_profile per source/dataset, evaluated per-action (never a
    single can_use boolean — see app.modules.rights.engine, added in P0 week 3).
    """

    __tablename__ = "rights_profile"
    __table_args__ = {"schema": "governance"}

    code: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")


class RightsGrant(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One row per (rights_profile, action) — deliberately dumb data with no
    business logic; all fail-closed evaluation lives in
    app.modules.rights.engine. permission_state follows RIGHTS-001's
    vocabulary (ALLOW | DENY | CONDITIONAL | LIMITED | UNKNOWN | EXPIRED).
    Only ALLOW permits for now — CONDITIONAL/LIMITED (e.g. an attribution
    obligation) aren't implemented yet and deny rather than silently
    granting; RIGHTS-001 RG-03 already requires UNKNOWN/EXPIRED to deny.
    """

    __tablename__ = "rights_grant"
    __table_args__ = (
        UniqueConstraint("rights_profile_id", "action", name="uq_rights_grant_profile_action"),
        {"schema": "governance"},
    )

    rights_profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("governance.rights_profile.id"), index=True
    )
    action: Mapped[str] = mapped_column(String(32))
    permission_state: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
