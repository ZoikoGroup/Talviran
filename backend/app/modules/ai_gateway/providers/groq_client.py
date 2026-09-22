"""Thin HTTP wrapper around Groq's chat completions API.

UNLIKE every other external connector in this codebase, this is NOT
live-verified - there is no GROQ_API_KEY configured yet (2026-09-22).
Written against Groq's well-established, publicly documented
OpenAI-compatible chat completions endpoint (a stable, long-standing API
shape Groq deliberately mirrors for drop-in compatibility), but treat
this as unverified until it's actually been called against a real key.
The corresponding AIModel row is seeded at CANDIDATE status, not
PRODUCTION, for exactly this reason - see models.py's status lifecycle.

Run a real call and confirm this module still matches reality before
trusting it, the same way gemini_client.py was built.
"""

from dataclasses import dataclass
from typing import Any

import httpx

_API_BASE = "https://api.groq.com/openai/v1"


class GroqGenerationError(Exception):
    """The API call itself failed (bad key, network, non-200, unexpected
    shape) - distinct from "no key configured", which is a config problem
    the caller checks before this is ever invoked.
    """


@dataclass(frozen=True)
class GroqGenerationResult:
    text: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


async def generate_content(
    client: httpx.AsyncClient, *, model_key: str, prompt: str, api_key: str
) -> GroqGenerationResult:
    response = await client.post(
        f"{_API_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model_key, "messages": [{"role": "user", "content": prompt}]},
        timeout=30.0,
    )
    if response.status_code != 200:
        raise GroqGenerationError(
            f"Groq chat/completions returned {response.status_code}: {response.text[:500]}"
        )
    body: dict[str, Any] = response.json()

    choices = body.get("choices")
    if not choices:
        raise GroqGenerationError(f"no choices in response: {body}")
    choice = choices[0]
    try:
        text = choice["message"]["content"]
    except KeyError as exc:
        raise GroqGenerationError(f"unexpected choice shape: {choice}") from exc

    usage = body.get("usage", {})
    return GroqGenerationResult(
        text=str(text),
        finish_reason=choice.get("finish_reason"),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    )
