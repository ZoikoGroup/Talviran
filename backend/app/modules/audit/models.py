"""audit schema — owned by this module. Not one of ENG-ARCH-003's named 13
modules; introduced as the sole writer of the `audit` schema so the
"cross-cutting audit trail" the architecture calls for still has exactly one
owner (every other module calls `record_event()` rather than writing here
directly, preserving the no-cross-module-writes rule).
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKeyMixin


class EventLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "event_log"
    __table_args__ = {"schema": "audit"}

    # No FKs on actor/subject: an audit row must survive independently of the
    # entity it describes (including across a later purge of that entity).
    occurred_at: Mapped[dt.datetime] = mapped_column(
        server_default=func.now(), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    actor_principal_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    subject_type: Mapped[str | None] = mapped_column(String(120))
    subject_id: Mapped[str | None] = mapped_column(String(200))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
