"""Thin HTTP wrapper around Google's Gemini generateContent API - verified
live on 2026-09-22 before this was written (same discipline as every
other external connector in this codebase).

Real findings from that verification, not assumed from documentation:
- `gemini-2.5-pro` and `gemini-2.5-flash` both 404 ("no longer available
  to new users") for this key/API version.
- `gemini-pro-latest` resolves to `gemini-3.1-pro` under the hood, which
  has ZERO free-tier quota (429 RESOURCE_EXHAUSTED, limit: 0) - the "pro"
  model line is entirely unavailable on this key's current tier.
- `gemini-flash-latest` intermittently 503s ("high demand").
- `gemini-flash-lite-latest` (-> `gemini-3.5-flash-lite`) works: real 200,
  real generated text. This is the only reliably-working model on this
  key right now - see app/modules/ai_gateway/models.py's seed data and
  the project memory note this is flagged in.

Response shape (confirmed live): candidates[0].content.parts[0].text,
candidates[0].finishReason, usageMetadata.{promptTokenCount,
candidatesTokenCount, totalTokenCount}.

(A6 hardening, 2026-09-23) `client.post` had no surrounding try/except -
a real network failure (timeout, DNS, connection reset) raised a bare
httpx exception neither this module nor gateway.py's
`except (GeminiGenerationError, GroqGenerationError)` caught, crashing
the whole `invoke_model` call instead of gracefully rejecting. Also a
real leak-risk: Gemini's own auth scheme puts `api_key` in the request
URL's query string, and some httpx exceptions embed the request URL in
their message - fixed by wrapping the call, re-raising as
GeminiGenerationError, and using only `type(exc).__name__`, never
`str(exc)`.
"""

from dataclasses import dataclass
from typing import Any

import httpx

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiGenerationError(Exception):
    """The API call itself failed (bad key, network, non-200, unexpected
    shape) - distinct from "no key configured", which is a config problem
    the caller checks before this is ever invoked.
    """


@dataclass(frozen=True)
class GeminiGenerationResult:
    text: str
    finish_reason: str | None
    prompt_token_count: int | None
    candidates_token_count: int | None
    total_token_count: int | None


async def generate_content(
    client: httpx.AsyncClient, *, model_key: str, prompt: str, api_key: str
) -> GeminiGenerationResult:
    try:
        response = await client.post(
            f"{_API_BASE}/models/{model_key}:generateContent",
            params={"key": api_key},
            json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        # A0/A1/A2 (gateway.py) only ever catch GeminiGenerationError, not
        # raw httpx exceptions - without this, a timeout/DNS/connection
        # failure would crash the whole invoke_model call instead of
        # gracefully rejecting (A3's "model unavailable -> alternate
        # route" needs this to fire at all). type(exc).__name__ only,
        # never str(exc) - the request URL carries api_key as a query
        # param (Gemini's own auth scheme), and some httpx exceptions
        # embed the request URL in their message.
        raise GeminiGenerationError(
            f"network error calling Gemini: {type(exc).__name__}"
        ) from exc
    if response.status_code != 200:
        raise GeminiGenerationError(
            f"Gemini generateContent returned {response.status_code}: {response.text[:500]}"
        )
    body: dict[str, Any] = response.json()

    candidates = body.get("candidates")
    if not candidates:
        raise GeminiGenerationError(f"no candidates in response: {body}")
    candidate = candidates[0]
    try:
        text = candidate["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise GeminiGenerationError(f"unexpected candidate shape: {candidate}") from exc

    usage = body.get("usageMetadata", {})
    return GeminiGenerationResult(
        text=str(text),
        finish_reason=candidate.get("finishReason"),
        prompt_token_count=usage.get("promptTokenCount"),
        candidates_token_count=usage.get("candidatesTokenCount"),
        total_token_count=usage.get("totalTokenCount"),
    )
