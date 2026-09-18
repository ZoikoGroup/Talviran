"""MON-001 §12.3's dead-man control, the testable half: record_heartbeat()
is called by the evaluator (scripts/run_monitoring_worker.py) on every
sweep; check_evaluator_health() is called by a genuinely separate process
(scripts/run_deadman_watcher.py). The two scripts never share execution -
that separation IS the control, per MON-001's own explicit doctrine:
"An evaluator process cannot be trusted to report that it has died."

No concrete staleness threshold is specified anywhere in MON-001 (see
models.py's docstring on the same gap for coverage) - max_staleness is a
required, explicit argument here rather than a hidden default, so the
caller (the watcher script) states its own threshold in one visible place
instead of it being buried in this module.
"""

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.monitoring.models import EvaluatorHeartbeat


async def record_heartbeat(session: AsyncSession, *, worker_id: str) -> None:
    heartbeat = (
        await session.execute(
            select(EvaluatorHeartbeat).where(EvaluatorHeartbeat.worker_id == worker_id)
        )
    ).scalar_one_or_none()
    now = dt.datetime.now(dt.UTC)
    if heartbeat is None:
        session.add(EvaluatorHeartbeat(worker_id=worker_id, last_heartbeat_at=now))
    else:
        heartbeat.last_heartbeat_at = now
    await session.flush()


@dataclass(frozen=True)
class EvaluatorHealthy:
    worker_id: str
    last_heartbeat_at: dt.datetime


@dataclass(frozen=True)
class EvaluatorDead:
    worker_id: str
    reason: str


@dataclass(frozen=True)
class EvaluatorUnknown:
    """Never heartbeated at all - distinct from EvaluatorDead (which means
    it heartbeated before and has since gone stale). A worker that has
    literally never run is a deployment problem, not a "recovered, then
    died again" one - the watcher script should word its page differently.
    """

    worker_id: str


async def check_evaluator_health(
    session: AsyncSession,
    *,
    worker_id: str,
    max_staleness: dt.timedelta,
    now: dt.datetime | None = None,
) -> EvaluatorHealthy | EvaluatorDead | EvaluatorUnknown:
    heartbeat = (
        await session.execute(
            select(EvaluatorHeartbeat).where(EvaluatorHeartbeat.worker_id == worker_id)
        )
    ).scalar_one_or_none()
    if heartbeat is None:
        return EvaluatorUnknown(worker_id=worker_id)

    moment = now or dt.datetime.now(dt.UTC)
    age = moment - heartbeat.last_heartbeat_at
    if age > max_staleness:
        return EvaluatorDead(
            worker_id=worker_id,
            reason=f"last heartbeat at {heartbeat.last_heartbeat_at.isoformat()}, {age} ago",
        )
    return EvaluatorHealthy(worker_id=worker_id, last_heartbeat_at=heartbeat.last_heartbeat_at)
