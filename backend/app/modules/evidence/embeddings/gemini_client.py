"""Thin HTTP wrapper around Google's Gemini embedding API
(gemini-embedding-001) - EVID-001 E3's semantic retrieval half.

Endpoint shape, response shape, and the outputDimensionality truncation
parameter were all confirmed live against the real API on 2026-09-21
before this was written (gemini-embedding-001's own default output is
3072 dimensions; 768 is requested explicitly via a real, documented API
parameter, not assumed) - not guessed from documentation, same discipline
as every other external connector in this codebase.
"""

import httpx

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768
_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiEmbeddingError(Exception):
    """The API call itself failed (bad key, network, non-200, unexpected
    shape) - distinct from "no key configured", which is a config problem
    the caller checks before this is ever invoked.
    """


async def embed_text(client: httpx.AsyncClient, *, text: str, api_key: str) -> list[float]:
    try:
        response = await client.post(
            f"{_API_BASE}/models/{EMBEDDING_MODEL}:embedContent",
            params={"key": api_key},
            json={
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": EMBEDDING_DIMENSIONS,
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        # A transport failure (DNS, connection reset, the 30s timeout
        # actually elapsing) is "network", one of the reasons this
        # class's own docstring already claims - wrapping it here fixes
        # both of this function's callers (embed_chunk and
        # search_chunks_by_semantic_query) in one place, rather than each
        # having to know to catch a bare httpx exception separately.
        raise GeminiEmbeddingError(f"Gemini embedContent request failed: {exc}") from exc
    if response.status_code != 200:
        raise GeminiEmbeddingError(
            f"Gemini embedContent returned {response.status_code}: {response.text[:500]}"
        )
    values = response.json()["embedding"]["values"]
    if len(values) != EMBEDDING_DIMENSIONS:
        raise GeminiEmbeddingError(
            f"expected {EMBEDDING_DIMENSIONS} dimensions, got {len(values)}"
        )
    return list(values)
