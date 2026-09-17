"""MON-001 §12.3's dead-man control, made real: a genuinely separate
process from scripts/run_monitoring_worker.py (the evaluator), watching
its heartbeat. This is not a shared library call from the same script -
running the check in the evaluator's own process would defeat the entire
point of the doctrine: "An evaluator process cannot be trusted to report
that it has died." Deploy this as its own process/host/scheduler in
production (§30's stage M2 groups this with coverage work, not with the
evaluator itself).

MON-001 gives no concrete staleness threshold or paging mechanism
anywhere (§12.3 is doctrine - independent failure domain, must page,
must create a coverage incident - not a wire format or a number). Two
honest choices made here, not hidden:
  - DEFAULT_MAX_STALENESS is 3x the worker's own --poll-seconds default
    (30s), i.e. 90s - a documented choice, not a MON-001 number.
  - "Paging" means writing a loud, structured line to this process's own
    stdout/stderr (exit code 1 on DEAD, so a real deployment can wire
    this into any monitoring/alerting stack's own "alert on nonzero exit"
    convention). Actually calling a third-party paging provider
    (PagerDuty/Opsgenie/a Slack webhook) needs real credentials this
    project doesn't have - faking that call would be worse than not
    having it, so it isn't here. This prints exactly what a real
    integration would need to send.

Run once (a cron/synthetic-check target - the natural mode, since a
missed run of the WATCHER ITSELF is exactly the kind of failure an
external scheduler, not this process, should catch):

    uv run python -m scripts.run_deadman_watcher

Run continuously (only if nothing external already schedules it):

    uv run python -m scripts.run_deadman_watcher --loop --poll-seconds 60
"""

import argparse
import asyncio
import datetime as dt
import sys

from app.core.db import get_session_factory
from app.modules.monitoring.heartbeat import EvaluatorDead, EvaluatorUnknown, check_evaluator_health

DEFAULT_MAX_STALENESS = dt.timedelta(seconds=90)


async def check_once(*, worker_id: str, max_staleness: dt.timedelta) -> int:
    factory = get_session_factory()
    async with factory() as session:
        result = await check_evaluator_health(
            session, worker_id=worker_id, max_staleness=max_staleness
        )

    if isinstance(result, EvaluatorDead):
        print(f"PAGE: evaluator {result.worker_id!r} is DEAD - {result.reason}", file=sys.stderr)
        return 1
    if isinstance(result, EvaluatorUnknown):
        print(
            f"PAGE: evaluator {result.worker_id!r} has never heartbeated - "
            "not yet deployed, or deployed and immediately failing",
            file=sys.stderr,
        )
        return 1

    print(f"OK: evaluator {result.worker_id!r} last heartbeat at {result.last_heartbeat_at}")
    return 0


async def run(
    *, worker_id: str, max_staleness: dt.timedelta, loop: bool, poll_seconds: float
) -> int:
    exit_code = await check_once(worker_id=worker_id, max_staleness=max_staleness)
    if not loop:
        return exit_code

    try:
        while True:
            await asyncio.sleep(poll_seconds)
            exit_code = await check_once(worker_id=worker_id, max_staleness=max_staleness)
    except KeyboardInterrupt:
        return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-id", default="monitoring-worker-1")
    parser.add_argument(
        "--max-staleness-seconds", type=float, default=DEFAULT_MAX_STALENESS.total_seconds()
    )
    parser.add_argument("--loop", action="store_true", help="keep polling instead of exiting")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    args = parser.parse_args()
    sys.exit(
        asyncio.run(
            run(
                worker_id=args.worker_id,
                max_staleness=dt.timedelta(seconds=args.max_staleness_seconds),
                loop=args.loop,
                poll_seconds=args.poll_seconds,
            )
        )
    )


if __name__ == "__main__":
    main()
