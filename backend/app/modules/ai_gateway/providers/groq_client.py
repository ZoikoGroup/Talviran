"""Thin HTTP wrapper around Groq's chat completions API.

Live-verified 2026-09-22 against a real GROQ_API_KEY. Two real findings,
neither assumed beforehand:

1. `llama-3.3-70b-versatile` (this module's originally-assumed model,
   and what scripts/seed_ai_gateway.py used to register) does not exist
   on this key's model list at all - a real GET /openai/v1/models call
   returned no such id. The actual available chat-capable models are
   `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.6-27b`,
   `qwen/qwen3.8-27b`, `allam-2-7b` (the rest of the list is audio/guard
   models: whisper-*, orpheus-*, llama-prompt-guard-*, not general chat).
   Registered `openai/gpt-oss-20b` for talvrin-go - fast, 0.5s round
   trip, matches the "fast everyday lookups" tier.
2. Groq's gpt-oss models are reasoning models: the real response's
   `choices[0].message` includes an extra `reasoning` field (the
   chain-of-thought) alongside `content`. This module's parsing already
   only reads `message["content"]`, so no code change was needed - just
   noting it so it isn't mistaken for a malformed response later.
3. Without an explicit `max_completion_tokens`, longer prompts (e.g. a
   grounded evidence prompt with several items) can hit `finish_reason:
   "length"` with ZERO content - the reasoning tokens alone exhaust
   whatever implicit cap applies, leaving nothing for the answer itself.
   Reproduced live 2026-09-22 (report of 5 Talvrin-scope queries run
   through both providers) and confirmed fixed by setting
   `max_completion_tokens=4096`: the same prompt that returned empty
   content came back complete (`finish_reason: "stop"`,
   `reasoning_tokens: 1912` of the 4096 budget).
4. (A6 hardening, 2026-09-23) `client.post` had no surrounding
   try/except - a real network failure (timeout, DNS, connection reset)
   raised a bare httpx exception that neither this module nor
   gateway.py's `except (GeminiGenerationError, GroqGenerationError)`
   caught, crashing the whole `invoke_model` call instead of gracefully
   rejecting. Fixed by wrapping the call and re-raising as
   GroqGenerationError.

The corresponding AIModel row is now PRODUCTION (models.py's status
lifecycle) - promoted only after this live proof, same governance
discipline scripts.approve_calculation_spec.py applies to calc specs.
"""

from dataclasses import dataclass
from typing import Any

import httpx

_API_BASE = "https://api.groq.com/openai/v1"
# Empirically chosen (see module docstring finding 3) - large enough that
# reasoning tokens on a grounded, multi-item evidence prompt don't crowd
# out the answer itself. Revisit if evidence bundles grow large enough to
# make this the binding constraint again.
_MAX_COMPLETION_TOKENS = 4096


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
    try:
        response = await client.post(
            f"{_API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model_key,
                "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": _MAX_COMPLETION_TOKENS,
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        # Same reasoning as gemini_client.py's identical guard: without
        # this, a timeout/DNS/connection failure crashes the whole
        # invoke_model call instead of gracefully rejecting (needed for
        # A3's "model unavailable -> alternate route" to fire at all).
        raise GroqGenerationError(f"network error calling Groq: {type(exc).__name__}") from exc
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
