from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import EventLog


async def record_event(
    session: AsyncSession,
    *,
    event_type: str,
    actor_principal_id: Any | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> EventLog:
    """The only sanctioned way another module writes to audit.event_log —
    callers pass their own session so the audit row commits atomically with
    the business change it describes.
    """
    event = EventLog(
        event_type=event_type,
        actor_principal_id=actor_principal_id,
        subject_type=subject_type,
        subject_id=subject_id,
        payload=payload,
    )
    session.add(event)
    return event
