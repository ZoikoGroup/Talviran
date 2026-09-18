"""check_evaluator_health's three outcomes: never heartbeated (unknown),
heartbeated recently (healthy), heartbeated too long ago (dead) - the
testable half of MON-001 §12.3's dead-man control.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.monitoring.heartbeat import (
    EvaluatorDead,
    EvaluatorHealthy,
    EvaluatorUnknown,
    check_evaluator_health,
    record_heartbeat,
)
from app.modules.monitoring.models import EvaluatorHeartbeat

_WORKER_ID = "test-worker"
_MAX_STALENESS = dt.timedelta(minutes=2)


async def test_never_heartbeated_is_unknown(db_session: AsyncSession) -> None:
    result = await check_evaluator_health(
        db_session, worker_id=_WORKER_ID, max_staleness=_MAX_STALENESS
    )
    assert isinstance(result, EvaluatorUnknown)


async def test_recent_heartbeat_is_healthy(db_session: AsyncSession) -> None:
    await record_heartbeat(db_session, worker_id=_WORKER_ID)
    await db_session.commit()

    result = await check_evaluator_health(
        db_session, worker_id=_WORKER_ID, max_staleness=_MAX_STALENESS
    )

    assert isinstance(result, EvaluatorHealthy)


async def test_stale_heartbeat_is_dead(db_session: AsyncSession) -> None:
    await record_heartbeat(db_session, worker_id=_WORKER_ID)
    await db_session.commit()

    result = await check_evaluator_health(
        db_session,
        worker_id=_WORKER_ID,
        max_staleness=_MAX_STALENESS,
        now=dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
    )

    assert isinstance(result, EvaluatorDead)
    assert "ago" in result.reason


async def test_re_recording_a_heartbeat_updates_the_same_row_not_a_new_one(
    db_session: AsyncSession,
) -> None:
    await record_heartbeat(db_session, worker_id=_WORKER_ID)
    await record_heartbeat(db_session, worker_id=_WORKER_ID)
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(EvaluatorHeartbeat).where(EvaluatorHeartbeat.worker_id == _WORKER_ID)
        )
    ).scalars().all()
    assert len(rows) == 1
