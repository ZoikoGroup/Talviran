"""SEC-001 §7 password controls. No database required."""

import pytest

from app.modules.identity.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    NullBreachScreen,
    PasswordPolicyError,
    check_policy,
    hash_password,
    sha1_prefix_suffix,
    verify_password,
)


def test_hash_is_argon2id() -> None:
    # The variant is not an implementation detail: §7 requires a memory-hard
    # algorithm, and argon2i/argon2d would both satisfy "argon2" while being
    # the wrong choice for password storage.
    assert hash_password("correct horse battery").startswith("$argon2id$")


def test_same_password_hashes_differently_every_time() -> None:
    """Unique salts, per §7 — identical passwords must not collide, or a
    dump reveals which users share one."""
    a = hash_password("correct horse battery")
    b = hash_password("correct horse battery")
    assert a != b


def test_plaintext_never_appears_in_the_hash() -> None:
    secret = "supersecretpassphrase1"
    assert secret not in hash_password(secret)


def test_correct_password_verifies() -> None:
    stored = hash_password("correct horse battery")
    assert verify_password(stored, "correct horse battery").ok


@pytest.mark.parametrize(
    "wrong",
    ["correct horse batter", "Correct horse battery", "", "  correct horse battery  "],
)
def test_wrong_password_fails(wrong: str) -> None:
    stored = hash_password("correct horse battery")
    assert not verify_password(stored, wrong).ok


def test_corrupt_hash_fails_closed_rather_than_raising() -> None:
    """A damaged row must read as a failed login, not a 500 — an attacker
    must not be able to distinguish the two, and an operational fault must
    never become an authentication bypass."""
    assert not verify_password("not-a-real-hash", "anything").ok
    assert not verify_password("", "anything").ok


def test_current_parameters_do_not_ask_for_rehash() -> None:
    stored = hash_password("correct horse battery")
    assert verify_password(stored, "correct horse battery").needs_rehash is False


def test_hash_from_weaker_parameters_is_flagged_for_rehash() -> None:
    """Login is the only moment the plaintext exists to upgrade with, so a
    hash made under older, cheaper settings must be detected there."""
    from argon2 import PasswordHasher

    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("pw")
    result = verify_password(weak, "pw")
    assert result.ok
    assert result.needs_rehash is True


def test_policy_enforces_only_a_length_floor() -> None:
    """§7: no composition rules that cost usability without buying security.
    A long passphrase of one character class must be accepted."""
    check_policy("a" * MIN_PASSWORD_LENGTH)
    check_policy("all lowercase words with no digits or symbols at all")


def test_policy_rejects_short_passwords() -> None:
    with pytest.raises(PasswordPolicyError):
        check_policy("a" * (MIN_PASSWORD_LENGTH - 1))


def test_policy_rejects_absurdly_long_passwords() -> None:
    """Bounded so a huge body cannot turn per-hash cost into a CPU attack."""
    with pytest.raises(PasswordPolicyError):
        check_policy("a" * (MAX_PASSWORD_LENGTH + 1))


def test_hashing_applies_the_policy() -> None:
    with pytest.raises(PasswordPolicyError):
        hash_password("short")


def test_breach_screen_sends_only_a_five_character_prefix() -> None:
    """k-anonymity: the password, and 35 of the 40 digest characters, must
    never leave the process."""
    password = "correct horse battery"
    prefix, suffix = sha1_prefix_suffix(password)
    assert len(prefix) == 5
    assert len(suffix) == 35
    assert password not in prefix
    assert (prefix + suffix).isupper()


async def test_null_breach_screen_accepts_everything() -> None:
    """The offline default must not silently block logins in environments
    with no outbound network."""
    assert await NullBreachScreen().is_compromised("password") is False
