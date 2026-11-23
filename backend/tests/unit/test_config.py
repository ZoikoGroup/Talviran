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

# Passed as explicit keyword arguments at each call site below, not splatted
# from a dict - Settings' __init__ signature (pydantic-settings' generated
# constructor) has many internal _cli_*/_secrets_dir-style parameters with
# specific non-str types, and `**dict[str, str]` makes mypy check a bare str
# value against every one of them, which it can never satisfy.
SUPABASE_URL = "https://example.supabase.co"
SUPABASE_ANON_KEY = "test-anon-key"


def test_localhost_frontend_url_is_fine_in_development() -> None:
    settings = Settings(
        supabase_url=SUPABASE_URL, supabase_anon_key=SUPABASE_ANON_KEY, environment="development"
    )
    assert settings.frontend_url == "http://localhost:5173"


def test_localhost_frontend_url_is_fine_in_test() -> None:
    settings = Settings(
        supabase_url=SUPABASE_URL, supabase_anon_key=SUPABASE_ANON_KEY, environment="test"
    )
    assert settings.frontend_url == "http://localhost:5173"


@pytest.mark.parametrize(
    "url", ["http://localhost:5173", "https://127.0.0.1:5173", "http://0.0.0.0:3000"]
)
def test_localhost_frontend_url_fails_closed_outside_development(url: str) -> None:
    with pytest.raises(ValidationError, match="frontend_url is still a localhost default"):
        Settings(
            supabase_url=SUPABASE_URL,
            supabase_anon_key=SUPABASE_ANON_KEY,
            environment="production",
            frontend_url=url,
        )


def test_a_real_origin_boots_fine_in_production() -> None:
    settings = Settings(
        supabase_url=SUPABASE_URL,
        supabase_anon_key=SUPABASE_ANON_KEY,
        environment="production",
        frontend_url="https://app.talvrin.com",
    )
    assert settings.frontend_url == "https://app.talvrin.com"
