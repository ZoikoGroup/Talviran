"""SEC-001 §8 session token handling. No database required."""

import datetime as dt

from app.modules.identity.tokens import (
    DEFAULT_ABSOLUTE_LIFETIME,
    DEFAULT_IDLE_TIMEOUT,
    generate_token,
    hash_token,
    is_expired,
    issue_session,
    slide_idle_expiry,
    tokens_match,
)

NOW = dt.datetime(2026, 9, 11, 12, 0, tzinfo=dt.UTC)


def test_tokens_are_unique() -> None:
    assert len({generate_token() for _ in range(500)}) == 500


def test_tokens_carry_meaningful_entropy() -> None:
    # 32 bytes base64url-encoded lands around 43 characters. A short token
    # here would mean someone reduced TOKEN_BYTES without thinking.
    assert len(generate_token()) >= 40


def test_the_raw_token_is_never_the_stored_value() -> None:
    """The point of the module: a dump of identity.session must not contain
    anything that can authenticate a request."""
    issued = issue_session(now=NOW)
    assert issued.token_hash != issued.token
    assert issued.token not in issued.token_hash
    assert len(issued.token_hash) == 64  # SHA-256 hex


def test_matching_is_by_digest() -> None:
    issued = issue_session(now=NOW)
    assert tokens_match(issued.token_hash, issued.token)


def test_a_different_token_does_not_match() -> None:
    issued = issue_session(now=NOW)
    assert not tokens_match(issued.token_hash, generate_token())
    assert not tokens_match(issued.token_hash, "")


def test_the_digest_itself_is_not_accepted_as_a_token() -> None:
    """Guards against a leaked digest being replayed straight back as the
    cookie value — it must hash again, not compare raw."""
    issued = issue_session(now=NOW)
    assert not tokens_match(issued.token_hash, issued.token_hash)


def test_hashing_is_deterministic() -> None:
    token = generate_token()
    assert hash_token(token) == hash_token(token)


def test_issue_sets_both_expiry_bounds() -> None:
    """§8 requires absolute *and* idle expiry. Absolute alone lets a stolen
    cookie live for weeks; idle alone lets an active attacker keep it
    forever."""
    issued = issue_session(now=NOW)
    assert issued.absolute_expiry == NOW + DEFAULT_ABSOLUTE_LIFETIME
    assert issued.idle_expiry == NOW + DEFAULT_IDLE_TIMEOUT
    assert issued.idle_expiry < issued.absolute_expiry


def test_a_live_session_is_not_expired() -> None:
    issued = issue_session(now=NOW)
    assert not is_expired(
        absolute_expiry=issued.absolute_expiry,
        idle_expiry=issued.idle_expiry,
        revoked_at=None,
        now=NOW + dt.timedelta(hours=1),
    )


def test_idle_timeout_expires_a_quiet_session() -> None:
    issued = issue_session(now=NOW)
    assert is_expired(
        absolute_expiry=issued.absolute_expiry,
        idle_expiry=issued.idle_expiry,
        revoked_at=None,
        now=NOW + DEFAULT_IDLE_TIMEOUT + dt.timedelta(seconds=1),
    )


def test_absolute_expiry_ends_even_an_active_session() -> None:
    issued = issue_session(now=NOW)
    assert is_expired(
        absolute_expiry=issued.absolute_expiry,
        # Idle window slid right up to the cap, i.e. continuously used.
        idle_expiry=issued.absolute_expiry,
        revoked_at=None,
        now=NOW + DEFAULT_ABSOLUTE_LIFETIME,
    )


def test_revocation_beats_every_other_check() -> None:
    """Server-side revocability is why sessions are rows and not
    self-contained signed tokens — so it must win unconditionally."""
    issued = issue_session(now=NOW)
    assert is_expired(
        absolute_expiry=issued.absolute_expiry,
        idle_expiry=issued.idle_expiry,
        revoked_at=NOW,
        now=NOW + dt.timedelta(seconds=1),
    )


def test_activity_slides_the_idle_window() -> None:
    issued = issue_session(now=NOW)
    later = NOW + dt.timedelta(days=3)
    assert slide_idle_expiry(
        absolute_expiry=issued.absolute_expiry, now=later
    ) == later + DEFAULT_IDLE_TIMEOUT


def test_sliding_never_exceeds_the_absolute_cap() -> None:
    """Without this clamp a session used once a day would live forever and
    the absolute bound would be decorative."""
    issued = issue_session(now=NOW)
    nearly_over = issued.absolute_expiry - dt.timedelta(minutes=5)
    assert (
        slide_idle_expiry(absolute_expiry=issued.absolute_expiry, now=nearly_over)
        == issued.absolute_expiry
    )
