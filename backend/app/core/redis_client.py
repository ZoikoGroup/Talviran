from redis.asyncio import Redis, from_url

from app.core.config import get_settings

_redis: Redis | None = None


def get_redis() -> Redis:
    """Process-level singleton, same caveat as app.core.db's cached engine:
    correct for the real app under one persistent event loop, wrong to
    reuse across pytest's per-test-function loops. Tests create their own
    client instead (see tests/integration/conftest.py).
    """
    global _redis
    if _redis is None:
        _redis = from_url(get_settings().redis_url, decode_responses=True)
    return _redis
