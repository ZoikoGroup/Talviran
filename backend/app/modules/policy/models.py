"""governance schema — see app.modules.rights.models for the shared-schema
rationale. `policy_decision` is the one table here that IS principal/account
scoped (it logs the PDP verdict for a specific request) and gets RLS.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

# KillSwitch and PolicyDecision below declare FKs to identity.principal /
# identity.account by string ("identity.principal.id"). SQLAlchemy only
# resolves those strings once the target model class has actually been
# imported somewhere in the process — it does NOT load them lazily on its
# own. Without this import, whether that FK resolves at all depends on
# whether some *unrelated* module happened to import app.modules.identity
# first (e.g. only true when a test file that imports it is also collected
# in the same pytest run) — a real bug caught by running a narrower test
# subset than usual. The module that declares the cross-schema FK is
# responsible for guaranteeing its target is loaded, not whoever imports it.
from app.modules.identity import models as _identity_models  # noqa: F401


class JurisdictionPolicy(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "jurisdiction_policy"
    __table_args__ = {"schema": "governance"}

    jurisdiction_code: Mapped[str] = mapped_column(String(8), index=True)
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    effective_from: Mapped[dt.datetime]
    effective_to: Mapped[dt.datetime | None] = mapped_column(default=None)


class CapabilityStatus(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "capability_status"
    __table_args__ = {"schema": "governance"}

    capability_code: Mapped[str] = mapped_column(String(120), index=True)
    jurisdiction_code: Mapped[str | None] = mapped_column(String(8), default=None)
    status: Mapped[str] = mapped_column(String(32), default="UNAVAILABLE")


class ActivationRecord(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "activation_record"
    __table_args__ = {"schema": "governance"}

    jurisdiction_code: Mapped[str] = mapped_column(String(8), index=True)
    operating_entity: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    effective_from: Mapped[dt.datetime]
    effective_to: Mapped[dt.datetime | None] = mapped_column(default=None)


class KillSwitch(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "kill_switch"
    __table_args__ = {"schema": "governance"}

    code: Mapped[str] = mapped_column(String(120), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    activated_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    activated_by_principal_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.principal.id"), default=None
    )
    reason: Mapped[str | None] = mapped_column(default=None)


class PolicyDecision(UUIDPrimaryKeyMixin, Base):
    """Every PDP verdict, fail-closed or not, is logged here — this is what
    lets a regulator-response reconstruction actually happen later (QE-001 /
    POL-001 audit requirement). Written by app.modules.policy.pdp, added P0
    week 3.
    """

    __tablename__ = "policy_decision"
    __table_args__ = {"schema": "governance"}

    request_id: Mapped[str] = mapped_column(String(64), index=True)
    principal_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.principal.id"), index=True, default=None
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.account.id"), index=True, default=None
    )
    decision: Mapped[str] = mapped_column(String(16))  # PERMIT | DENY
    reason_codes: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    allowed_output_type: Mapped[str | None] = mapped_column(String(64), default=None)
    obligations: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    evaluated_at: Mapped[dt.datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
