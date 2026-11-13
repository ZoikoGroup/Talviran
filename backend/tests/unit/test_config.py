"""Settings' environment-conditional validation.

frontend_url feeds password-reset links (identity/service.py),
organization-invite links (organization.py) and Stripe checkout return URLs
(commercial/service.py). Its localhost default is correct for local
development but must never silently reach a real deployment - see bug T9's
"reset link opens localhost" symptom, and CookiePolicy.for_environment for
the same fail-closed shape this mirrors.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

REQUIRED = {"supabase_url": "https://example.supabase.co", "supabase_anon_key": "test-anon-key"}


def test_localhost_frontend_url_is_fine_in_development() -> None:
    settings = Settings(**REQUIRED, environment="development")
    assert settings.frontend_url == "http://localhost:5173"


def test_localhost_frontend_url_is_fine_in_test() -> None:
    settings = Settings(**REQUIRED, environment="test")
    assert settings.frontend_url == "http://localhost:5173"


@pytest.mark.parametrize(
    "url", ["http://localhost:5173", "https://127.0.0.1:5173", "http://0.0.0.0:3000"]
)
def test_localhost_frontend_url_fails_closed_outside_development(url: str) -> None:
    with pytest.raises(ValidationError, match="frontend_url is still a localhost default"):
        Settings(**REQUIRED, environment="production", frontend_url=url)


def test_a_real_origin_boots_fine_in_production() -> None:
    settings = Settings(
        **REQUIRED, environment="production", frontend_url="https://app.talvrin.com"
    )
    assert settings.frontend_url == "https://app.talvrin.com"
