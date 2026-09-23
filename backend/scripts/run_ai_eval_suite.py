"""Runs the AI Gateway's adversarial red-team suite (P4b AI-001 A4)
against a real task_type, live, through the real Gateway.

Run with:

    uv run python -m scripts.run_ai_eval_suite talvrin-go
    uv run python -m scripts.run_ai_eval_suite talvrin-pro

Requires GROQ_API_KEY/GEMINI_API_KEY as applicable in .env - this is a
live run against real providers (AI-G15: "perimeter adversarial: 0
failures"), not a mocked check. Persists one AIEvalRun row per run.
"""

import asyncio
import sys

import httpx
from dotenv import dotenv_values

from app.core.db import get_session_factory
from app.modules.ai_gateway.eval_suite import run_eval_suite

_JURISDICTION = "GB"


async def main(task_type: str) -> None:
    env = dotenv_values(".env")
    raw_keys = {"gemini": env.get("GEMINI_API_KEY"), "groq": env.get("GROQ_API_KEY")}
    api_keys = {code: key for code, key in raw_keys.items() if key}
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
