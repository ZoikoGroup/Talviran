"""AI Gateway operations CLI (P4b AI-001 A5) - kill-switch management
and route health, the ops-facing tooling AI-001 §27 wants, in the same
script-based form scripts/approve_calculation_spec.py and
scripts/seed_ai_gateway.py already use (see app/modules/ai_gateway/ops.py
for why this is a script, not an admin API endpoint).

Run with:

    uv run python -m scripts.ai_gateway_ops status
    uv run python -m scripts.ai_gateway_ops killswitch-on ai_gateway.global --reason "incident 123"
    uv run python -m scripts.ai_gateway_ops killswitch-off ai_gateway.global
"""

import argparse
import asyncio

from app.core.db import get_session_factory
from app.modules.ai_gateway.ops import activate_kill_switch, deactivate_kill_switch, get_health


async def _status() -> None:
    factory = get_session_factory()
    async with factory() as session:
        health = await get_health(session)

    print(f"Global kill switch active: {health.global_killswitch_active}")
    if not health.routes:
        print("No routes registered.")
        return
    for route in health.routes:
        flags = []
        if route.provider_killswitched:
            flags.append("PROVIDER KILLED")
        if route.model_killswitched:
            flags.append("MODEL KILLED")
        flag_text = f" [{', '.join(flags)}]" if flags else ""
        print(
            f"  {route.task_type} (priority {route.priority}): "
            f"{route.provider_code}/{route.model_key} "
            f"(provider={route.provider_status}, model={route.model_status}) "
            f"- {route.recent_errors}/{route.recent_executions} recent errors{flag_text}"
        )


async def _killswitch_on(code: str, reason: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        await activate_kill_switch(session, code=code, reason=reason)
    print(f"Kill switch {code!r} activated: {reason!r}")


async def _killswitch_off(code: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        existed = await deactivate_kill_switch(session, code=code)
    print(f"Kill switch {code!r} deactivated." if existed else f"No such kill switch {code!r}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show route health and kill-switch state.")

    on_parser = subparsers.add_parser("killswitch-on", help="Activate a kill switch.")
    on_parser.add_argument("code")
    on_parser.add_argument("--reason", required=True)

    off_parser = subparsers.add_parser("killswitch-off", help="Deactivate a kill switch.")
    off_parser.add_argument("code")

    args = parser.parse_args()
    if args.command == "status":
        asyncio.run(_status())
    elif args.command == "killswitch-on":
        asyncio.run(_killswitch_on(args.code, args.reason))
    elif args.command == "killswitch-off":
        asyncio.run(_killswitch_off(args.code))


if __name__ == "__main__":
    main()
