import httpx

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Process-level singleton, same shape and the same caveat as
    app.core.redis_client's cached client: correct for the real app under one
    persistent event loop, wrong to reuse across pytest's per-test-function
    loops. Tests inject their own client — real for a live Supabase check,
    or backed by a fake transport otherwise (see
    tests/integration/conftest.py) — via FastAPI's dependency override rather
    than this singleton.

    Used for outbound calls to Supabase Auth (identity/supabase_auth.py). A
    shared client reuses its connection pool across requests instead of
    paying a fresh TCP/TLS handshake to Supabase on every sign-in.
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client
