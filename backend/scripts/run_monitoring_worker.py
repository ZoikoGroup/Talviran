"""The evaluator process itself (MON-001's own term) - the periodic sweep
that runs every ARMED rule, creates/delivers alerts, and records
coverage. This is the process scripts/run_deadman_watcher.py watches from
a genuinely separate script - see that file's own docstring for why "the
same script also does the watching" would defeat the whole point of the
doctrine (MON-001 §12.3: "An evaluator process cannot be trusted to
report that it has died").

No scheduler exists yet (a P3 scope limit noted throughout this module),
so this sweeps every ARMED rule on every run rather than being triggered
per-fact - relying on evaluate_rule_version's own idempotency (MON-001
§7.1's evaluation_key) to make a redundant sweep over an unchanged fact a
cheap no-op, not wasted work or a duplicate alert.

Rules are RLS-scoped per account; this worker is not "acting as" any one
user, so it iterates every identity.account and applies that account's
own RLS context before touching its rules - the same per-tenant iteration
shape any RLS-based multi-tenant background job needs, not a special case.

Run once (a cron target):

    uv run python -m scripts.run_monitoring_worker

Run continuously with a heartbeat (what a real deployment would run):

    uv run python -m scripts.run_monitoring_worker --loop --poll-seconds 30
"""

import argparse
import asyncio
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.identity.models import Account, Principal
from app.modules.identity.service import apply_rls_context
from app.modules.monitoring.alerts import AlertCreated, create_alert_for_evaluation
from app.modules.monitoring.coverage import record_successful_evaluation
from app.modules.monitoring.delivery import deliver_alert
from app.modules.monitoring.heartbeat import record_heartbeat
from app.modules.monitoring.models import STATUS_ARMED, MonitoringRuleVersion
from app.modules.monitoring.rule_engine import RuleEvaluationRecorded, evaluate_rule_version

WORKER_ID = "monitoring-worker-1"
TRIGGER_TYPE_SCHEDULED_SWEEP = "SCHEDULED_SWEEP"


async def _sweep_account(
    session: AsyncSession, *, account_id: uuid.UUID, principal_id: uuid.UUID
) -> int:
    await apply_rls_context(session, account_id=account_id, principal_id=principal_id)
    rule_versions = (
        await session.execute(
            select(MonitoringRuleVersion).where(MonitoringRuleVersion.status == STATUS_ARMED)
        )
    ).scalars().all()

    processed = 0
    for rule_version in rule_versions:
        evaluation = await evaluate_rule_version(
            session,
            rule_version_id=rule_version.id,
            trigger_type=TRIGGER_TYPE_SCHEDULED_SWEEP,
            trigger_id=None,
        )
        if not isinstance(evaluation, RuleEvaluationRecorded):
            continue

        # Each commit ends the transaction that held app.account_id (it's
        # is_local=true, transaction-scoped) - re-apply immediately after,
        # every time, or the next RLS-scoped write silently affects zero
        # rows instead of erroring (the exact bug found and fixed in
        # monitoring/service.py earlier - same failure mode, same fix).
        await session.commit()
        await apply_rls_context(session, account_id=account_id, principal_id=principal_id)

        await record_successful_evaluation(
            session, rule_evaluation_id=evaluation.rule_evaluation_id
        )
        alert = await create_alert_for_evaluation(
            session, rule_evaluation_id=evaluation.rule_evaluation_id
        )
        if isinstance(alert, AlertCreated):
            await deliver_alert(session, alert_id=alert.alert_id)

        await session.commit()
        await apply_rls_context(session, account_id=account_id, principal_id=principal_id)
        processed += 1

    return processed


async def sweep_once() -> int:
    factory = get_session_factory()
    total = 0
    async with factory() as session:
        await record_heartbeat(session, worker_id=WORKER_ID)
        await session.commit()

        account_ids = (await session.execute(select(Account.id))).scalars().all()
        for account_id in account_ids:
            # identity.principal has RLS keyed on app.account_id alone
            # (migration 0002) - it must already be set before this lookup
            # can see any row at all, principal_id or not. A placeholder
            # here is fine: only app.account_id matters for this specific
            # policy, and the real principal_id gets applied right after.
            await apply_rls_context(session, account_id=account_id, principal_id=account_id)
            principal_id = (
                await session.execute(
                    select(Principal.id).where(Principal.account_id == account_id).limit(1)
                )
            ).scalar_one_or_none()
            if principal_id is None:
                continue
            total += await _sweep_account(
                session, account_id=account_id, principal_id=principal_id
            )
    return total


async def run(*, loop: bool, poll_seconds: float) -> int:
    processed = await sweep_once()
    print(f"Swept {processed} rule evaluation(s).")
    if not loop:
        return 0

    print(f"Polling every {poll_seconds}s (Ctrl+C to stop)...")
    try:
        while True:
            await asyncio.sleep(poll_seconds)
            processed = await sweep_once()
            if processed:
                print(f"Swept {processed} rule evaluation(s).")
    except KeyboardInterrupt:
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true", help="keep polling instead of exiting")
    parser.add_argument(
        "--poll-seconds", type=float, default=30.0, help="seconds between sweeps in --loop mode"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(loop=args.loop, poll_seconds=args.poll_seconds)))


if __name__ == "__main__":
    main()
