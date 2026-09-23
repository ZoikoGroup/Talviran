"""Runs the AI Gateway's adversarial red-team suite (P4b AI-001 A4)
against a real task_type, live, through the real Gateway.

Run with:

    uv run python -m scripts.run_ai_eval_suite talvrin-go
    uv run python -m scripts.run_ai_eval_suite talvrin-pro

Requires GROQ_API_KEY/GEMINI_API_KEY as applicable - this is a live run
against real providers (AI-G15: "perimeter adversarial: 0 failures"),
not a mocked check. Persists one AIEvalRun row per run.

Reads keys via app.core.config.get_settings() (real environment
variables, falling back to a local .env), NOT a hand-rolled
dotenv_values(".env") read - this script is meant to run in CI (a
future ai-eval-gate.yml workflow), where secrets arrive as real env vars
and no .env file exists at all. A version of this script that only read
a literal .env file would silently run with zero configured keys in
CI - see the fail-fast check below for why that must never look like a
green run.
"""

import asyncio
import sys

import httpx

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.modules.ai_gateway.eval_suite import run_eval_suite

_JURISDICTION = "GB"


async def main(task_type: str) -> None:
    settings = get_settings()
    raw_keys = {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key}
    api_keys = {code: key for code, key in raw_keys.items() if key}
    if not api_keys:
        # _grade() treats every InvokeRejected as a safe "PASS" (a real
        # refusal IS the correct outcome for an adversarial case) - which
        # means a run with zero configured keys would report every case
        # as "safely refused" and exit 0, a false green that tested
        # nothing at all. Fail loud instead, before running anything.
        print(
            "ERROR: no GEMINI_API_KEY or GROQ_API_KEY configured - refusing to "
            "run, since every case would vacuously \"pass\" without ever "
            "reaching a provider. Set at least one before running this suite."
        )
        sys.exit(2)

    factory = get_session_factory()
    async with factory() as session, httpx.AsyncClient() as http:
        outcomes = await run_eval_suite(
            session, task_type=task_type, http=http, api_keys=api_keys,
            jurisdiction_code=_JURISDICTION,
        )

    failed = [o for o in outcomes if not o.passed]
    for o in outcomes:
        mark = "PASS" if o.passed else "FAIL"
        print(f"[{mark}] {o.case_id} ({o.category}): {o.detail}")

    print(f"\n{len(outcomes) - len(failed)}/{len(outcomes)} passed.")
    if failed:
        print(f"{len(failed)} FAILURE(S) - see above.")
        sys.exit(1)


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "talvrin-go"
    asyncio.run(main(task))
