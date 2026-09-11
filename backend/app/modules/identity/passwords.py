"""Password hashing and policy (SEC-001 §7).

The spec's rules, and how they land here:

- "Passwords stored only with a modern memory-hard password hashing algorithm
  and unique salts" — Argon2id. `argon2-cffi` salts every hash itself, so
  there is no salt handling to get wrong.
- "Do not impose composition rules that reduce usability without security
  benefit" — hence a length floor and nothing else. No "must contain a
  symbol", no forced mixed case.
- "Screen against known compromised/common passwords" — `BreachScreen` is the
  seam for that. The real implementation calls Have I Been Pwned's range API,
  which is k-anonymous (only the first five hex characters of the SHA-1 ever
  leave this process, never the password). It is a Protocol so tests and
  offline environments can substitute a local list.
- "No periodic password rotation absent compromise/risk trigger" — there is
  deliberately no `password_expires_at` anywhere in this module.

Verification returns a `VerifyResult` rather than a bare bool so the caller
learns whether the stored hash needs upgrading: Argon2 parameters are expected
to harden over time, and a login is the only moment the plaintext is available
to rehash with.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# NIST SP 800-63B-4 sets 8 as the floor for a memorised secret. The upper bound
# exists only to stop a multi-megabyte body becoming a CPU exhaustion vector —
# Argon2's cost is per-hash, but hashing is not free.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 4096

# OWASP's Argon2id baseline (19 MiB, 2 iterations, 1 lane). Memory cost is the
# parameter that actually resists GPU cracking; raising `time_cost` alone buys
# comparatively little.
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19 * 1024,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


class PasswordPolicyError(ValueError):
    """Raised when a password cannot be accepted. The message is user-facing."""


class BreachScreen(Protocol):
    """Returns True when a password is known to have appeared in a breach."""

    async def is_compromised(self, password: str) -> bool: ...


class NullBreachScreen:
    """Accepts everything. For tests and for local development only —
    production wires the Have I Been Pwned range client instead."""

    async def is_compromised(self, password: str) -> bool:  # noqa: ARG002
        return False


def sha1_prefix_suffix(password: str) -> tuple[str, str]:
    """Splits the SHA-1 the way the k-anonymity range API expects: the first
    five characters are sent, the remaining thirty-five never leave here."""
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()  # noqa: S324
    return digest[:5], digest[5:]


def check_policy(password: str) -> None:
    """Raises PasswordPolicyError when the password fails the length rules.

    Deliberately not a bool: a caller that forgets to check a bool fails open,
    and this is the wrong place for that to be possible.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
        )


def hash_password(password: str) -> str:
    """Returns a PHC-format Argon2id hash. Parameters are embedded in the
    string, so a future cost increase can still verify today's hashes."""
    check_policy(password)
    return _hasher.hash(password)


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    #: True when the stored hash used weaker parameters than current policy.
    needs_rehash: bool = False


def verify_password(stored_hash: str, password: str) -> VerifyResult:
    """Constant-time-ish verification that never raises on a wrong password.

    A corrupt or unrecognised hash is treated as a failed login, not as a
    server error — an attacker must not be able to tell the two apart, and an
    operational problem must not become an authentication bypass.
    """
    try:
        _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return VerifyResult(ok=False)

    try:
        needs_rehash = _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        needs_rehash = True
    return VerifyResult(ok=True, needs_rehash=needs_rehash)
