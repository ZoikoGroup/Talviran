"""identity/supabase_auth.py against the exact response shapes GoTrue is
known to return — most observed live against the real project this codebase
is configured against (see that module's docstring), one (the nested,
immediate-session signup shape) only documented, since observing it live
requires the project's "Confirm email" setting to actually be off. Each test
here builds a single canned response with `httpx.MockTransport` rather than
going through the database or the fuller FakeSupabaseAuth in
tests/integration/conftest.py, which only exercises one signup shape (the
one convenient for a fake user store) — these are the complement, proving
the client itself parses both.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.core.config import Settings
from app.modules.identity import supabase_auth

SETTINGS = Settings(
    supabase_url="https://example.supabase.co",
    supabase_anon_key="test-anon-key",
)


def _client(response: httpx.Response) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response))


# ---------------------------------------------------------------- sign up


async def test_sign_up_accepts_the_top_level_shape() -> None:
    """Observed live with email confirmation on: the user's own fields at
    the top level, no session."""
    user_id = str(uuid.uuid4())
    async with _client(
        httpx.Response(200, json={"id": user_id, "email": "a@example.com", "identities": [{}]})
    ) as client:
        user = await supabase_auth.sign_up(
            client, email="a@example.com", password="correct-horse-9", settings=SETTINGS
        )
    assert str(user.id) == user_id
    assert user.email == "a@example.com"


async def test_sign_up_accepts_the_nested_shape() -> None:
    """Documented behaviour with email confirmation off (this product's
    mode): the user nested under "user" alongside an immediate "session"."""
    user_id = str(uuid.uuid4())
    async with _client(
        httpx.Response(
            200,
            json={
                "access_token": "...",
                "session": {"access_token": "..."},
                "user": {"id": user_id, "email": "a@example.com", "identities": [{}]},
            },
        )
    ) as client:
        user = await supabase_auth.sign_up(
            client, email="a@example.com", password="correct-horse-9", settings=SETTINGS
        )
    assert str(user.id) == user_id
    assert user.email == "a@example.com"


async def test_sign_up_rejects_a_duplicate_email() -> None:
    """The empty `identities` array is GoTrue's signal for this, at 200 not
    4xx — confirmed live against the real project."""
    async with _client(
        httpx.Response(
            200, json={"id": str(uuid.uuid4()), "email": "a@example.com", "identities": []}
        )
    ) as client:
        with pytest.raises(supabase_auth.EmailAlreadyRegistered):
            await supabase_auth.sign_up(
                client, email="a@example.com", password="correct-horse-9", settings=SETTINGS
            )


async def test_sign_up_rejects_a_weak_password() -> None:
    """422 weak_password, confirmed live against the real project — its
    actual minimum (6 chars here) is a project setting, not this client's
    business to second-guess."""
    async with _client(
        httpx.Response(
            422,
            json={
                "code": 422,
                "error_code": "weak_password",
                "msg": "Password should be at least 6 characters.",
            },
        )
    ) as client:
        with pytest.raises(supabase_auth.WeakPassword):
            await supabase_auth.sign_up(
                client, email="a@example.com", password="short", settings=SETTINGS
            )


async def test_sign_up_raises_on_an_unrecognised_body() -> None:
    """A 200 with neither shape is a contract change worth knowing about
    loudly, not a silent None or KeyError."""
    async with _client(httpx.Response(200, json={"unexpected": "shape"})) as client:
        with pytest.raises(supabase_auth.SupabaseUnavailable):
            await supabase_auth.sign_up(
                client, email="a@example.com", password="correct-horse-9", settings=SETTINGS
            )


# ---------------------------------------------------------------- sign in


async def test_sign_in_returns_the_user_on_success() -> None:
    user_id = str(uuid.uuid4())
    async with _client(
        httpx.Response(
            200,
            json={"access_token": "...", "user": {"id": user_id, "email": "a@example.com"}},
        )
    ) as client:
        user = await supabase_auth.sign_in_with_password(
            client, email="a@example.com", password="correct-horse-9", settings=SETTINGS
        )
    assert str(user.id) == user_id


async def test_sign_in_rejects_invalid_credentials() -> None:
    """Confirmed live: wrong password and unknown address both come back
    as this one error code — the enumeration resistance SEC-001 §7.1 wants,
    for free."""
    async with _client(
        httpx.Response(
            400, json={"code": 400, "error_code": "invalid_credentials", "msg": "..."}
        )
    ) as client:
        with pytest.raises(supabase_auth.InvalidCredentials):
            await supabase_auth.sign_in_with_password(
                client, email="a@example.com", password="wrong", settings=SETTINGS
            )


async def test_sign_in_distinguishes_email_not_confirmed() -> None:
    """Confirmed live as a genuinely distinct error code from
    invalid_credentials — folding it in would be less honest, not more
    secure, since GoTrue's own API already exposes the distinction."""
    async with _client(
        httpx.Response(
            400, json={"code": 400, "error_code": "email_not_confirmed", "msg": "..."}
        )
    ) as client:
        with pytest.raises(supabase_auth.EmailNotConfirmed):
            await supabase_auth.sign_in_with_password(
                client, email="a@example.com", password="correct-horse-9", settings=SETTINGS
            )


# ------------------------------------------------------------ reset token


async def test_update_password_returns_the_user_on_success() -> None:
    user_id = str(uuid.uuid4())
    async with _client(
        httpx.Response(200, json={"id": user_id, "email": "a@example.com"})
    ) as client:
        user = await supabase_auth.update_password(
            client,
            access_token="a-real-recovery-token",
            new_password="Brand-New-Horse-9",
            settings=SETTINGS,
        )
    assert str(user.id) == user_id


async def test_update_password_rejects_a_bad_token() -> None:
    """403 bad_jwt, confirmed live against the real project for a malformed
    bearer — this client treats any 4xx here as an invalid reset token
    rather than pattern-matching one specific message."""
    async with _client(
        httpx.Response(
            403, json={"code": 403, "error_code": "bad_jwt", "msg": "invalid JWT"}
        )
    ) as client:
        with pytest.raises(supabase_auth.InvalidResetToken):
            await supabase_auth.update_password(
                client,
                access_token="garbage",
                new_password="Brand-New-Horse-9",
                settings=SETTINGS,
            )


async def test_update_password_rejects_a_weak_new_password() -> None:
    async with _client(
        httpx.Response(
            422,
            json={
                "code": 422,
                "error_code": "weak_password",
                "msg": "Password should be at least 6 characters.",
            },
        )
    ) as client:
        with pytest.raises(supabase_auth.WeakPassword):
            await supabase_auth.update_password(
                client,
                access_token="a-real-recovery-token",
                new_password="short",
                settings=SETTINGS,
            )


# ---------------------------------------------------------------- recover


async def test_request_password_reset_never_raises_for_an_unknown_address() -> None:
    """Confirmed live: 200 {} either way."""
    async with _client(httpx.Response(200, json={})) as client:
        await supabase_auth.request_password_reset(
            client, email="nobody@example.com", settings=SETTINGS
        )
