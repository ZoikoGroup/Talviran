"""P2's real out-of-process calculation-job consumer: drains
calculation.calculation_job, running each PENDING job through
compute_and_persist_model_implied_price via job_queue.run_next_job. A
plain Postgres poll-loop, not a broker - see
app/modules/calculation/pipeline/job_queue.py's docstring for why that's
the right scale for this pack today.

Run once (drains whatever is queued right now, then exits - the natural
mode for a cron job or a manual dev-workflow step):

    uv run python -m scripts.run_calculation_worker

Run continuously (polls for new jobs; a real deployment would run this
as its own long-lived process, never in the same process as the API):

    uv run python -m scripts.run_calculation_worker --loop --poll-seconds 5
"""

import argparse
import asyncio
import sys

from app.core.db import get_session_factory
from app.modules.calculation.pipeline.job_queue import run_next_job


async def drain_once() -> int:
    """Runs every currently-PENDING job to completion. Returns the count
    processed. Each job gets its own session/transaction (job_queue.
    run_next_job commits internally), so one job's failure can never roll
    back another's already-committed result.
    """
    factory = get_session_factory()
    processed = 0
    while True:
        async with factory() as session:
            result = await run_next_job(session)
        if result is None:
            return processed
        processed += 1
        print(f"  job {result.job_id}: {result.outcome}")


async def run(*, loop: bool, poll_seconds: float) -> int:
    processed = await drain_once()
    print(f"Drained {processed} job(s).")
    if not loop:
        return 0

    print(f"Polling every {poll_seconds}s for new jobs (Ctrl+C to stop)...")
    try:
        while True:
            await asyncio.sleep(poll_seconds)
            processed = await drain_once()
            if processed:
                print(f"Drained {processed} job(s).")
    except KeyboardInterrupt:
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--loop", action="store_true", help="keep polling for new jobs instead of exiting"
    )
    parser.add_argument(
        "--poll-seconds", type=float, default=5.0, help="seconds between polls in --loop mode"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(loop=args.loop, poll_seconds=args.poll_seconds)))


if __name__ == "__main__":
    main()
