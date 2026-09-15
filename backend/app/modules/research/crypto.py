"""Envelope encryption for user research content (SEC-001 §15).

The shape SEC-001 §15.1 asks for::

    Regional KMS key  ──encrypts──▶  Data Encryption Key  ──encrypts──▶  field

so that "copying ciphertext without authorised key access does not grant
plaintext access". Three consequences drive the design here:

1. **The DEK is per account, not per row or per deployment.** Per-deployment
   would make one leaked key total; per-row would mean a KMS call per message,
   which is both slow and expensive. Per-account bounds the blast radius to a
   single tenant and makes §15.2 cryptographic erasure meaningful — destroy one
   account's wrapped DEK and that account's content is unrecoverable, without
   rewriting anyone else's rows.

2. **Wrapping is pluggable.** Production wraps with Cloud KMS; local
   development and CI cannot reach it and must not require it. `KeyWrapper` is
   the seam, mirroring the `BreachScreen` protocol in identity.passwords.

3. **The plaintext DEK is never persisted.** Only the wrapped form goes to the
   database, so a database dump alone yields nothing.

AES-256-GCM is used for the content itself: authenticated, so a tampered
ciphertext fails loudly rather than decrypting to rubbish, and nonce-misuse is
avoided by generating a fresh random 96-bit nonce per encryption (never a
counter, which would repeat across replicas).
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

#: AES-256. 32 bytes of DEK, 12-byte nonce as recommended for GCM.
DEK_BYTES = 32
NONCE_BYTES = 12

#: Bumped if the wire format below ever changes, so old rows stay readable.
ENVELOPE_VERSION = 1


class DecryptionFailed(Exception):
    """Ciphertext did not authenticate under the supplied key.

    Raised for a wrong key, a truncated value and a tampered one alike — the
    distinction is not knowable from GCM's tag check, and is not useful to a
    caller anyway.
    """


class KeyWrapper(Protocol):
    """Wraps and unwraps data encryption keys.

    Deliberately narrow: the wrapper never sees plaintext content, only keys.
    """

    @property
    def key_name(self) -> str:
        """Identifies the wrapping key, recorded alongside the ciphertext so a
        rotated or re-homed key can still be found."""
        ...

    def wrap(self, dek: bytes) -> bytes: ...

    def unwrap(self, wrapped: bytes) -> bytes: ...


class LocalKeyWrapper:
    """Development and test wrapper.

    Wraps with AES-GCM under a key taken from configuration rather than a KMS.
    This is a genuine encryption boundary — it is not a no-op — but the wrapping
    key sits in the environment, so it protects against a leaked database dump
    and *not* against someone who already holds the application's configuration.
    Production uses the Cloud KMS wrapper, where key use is a separate,
    audited permission (SEC-001 §15: "key-use permission separate from
    ciphertext access").
    """

    def __init__(self, master_key: bytes, *, key_name: str = "local/dev") -> None:
        if len(master_key) != DEK_BYTES:
            raise ValueError(
                f"master key must be {DEK_BYTES} bytes, got {len(master_key)}"
            )
        self._aead = AESGCM(master_key)
        self._key_name = key_name

    @property
    def key_name(self) -> str:
        return self._key_name

    def wrap(self, dek: bytes) -> bytes:
        nonce = os.urandom(NONCE_BYTES)
        return nonce + self._aead.encrypt(nonce, dek, None)

    def unwrap(self, wrapped: bytes) -> bytes:
        nonce, body = wrapped[:NONCE_BYTES], wrapped[NONCE_BYTES:]
        try:
            return self._aead.decrypt(nonce, body, None)
        except InvalidTag as exc:
            raise DecryptionFailed("could not unwrap the data key") from exc

    @classmethod
    def from_base64(cls, encoded: str, *, key_name: str = "local/dev") -> LocalKeyWrapper:
        return cls(base64.b64decode(encoded), key_name=key_name)


@dataclass(frozen=True)
class Envelope:
    """A wrapped DEK and the name of the key that wrapped it."""

    wrapped_dek: bytes
    key_name: str
    version: int = ENVELOPE_VERSION


def new_dek() -> bytes:
    """A fresh 256-bit data encryption key from the OS CSPRNG."""
    return os.urandom(DEK_BYTES)


def create_envelope(wrapper: KeyWrapper) -> tuple[bytes, Envelope]:
    """Mints a DEK and returns it alongside its wrapped form.

    The plaintext DEK is the first element and must stay in memory only.
    """
    dek = new_dek()
    return dek, Envelope(wrapped_dek=wrapper.wrap(dek), key_name=wrapper.key_name)


def open_envelope(wrapper: KeyWrapper, envelope: Envelope) -> bytes:
    if envelope.version != ENVELOPE_VERSION:
        raise DecryptionFailed(
            f"unsupported envelope version {envelope.version}"
        )
    return wrapper.unwrap(envelope.wrapped_dek)


def encrypt(dek: bytes, plaintext: str, *, aad: bytes | None = None) -> bytes:
    """Encrypts UTF-8 text, returning `nonce || ciphertext || tag`.

    `aad` binds the ciphertext to its context — the conversation id, in
    practice. A row moved to another conversation then fails to decrypt rather
    than silently surfacing under the wrong parent.
    """
    nonce = os.urandom(NONCE_BYTES)
    body = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return nonce + body


def decrypt(dek: bytes, blob: bytes, *, aad: bytes | None = None) -> str:
    if len(blob) <= NONCE_BYTES:
        raise DecryptionFailed("ciphertext is too short to contain a nonce")
    nonce, body = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    try:
        return AESGCM(dek).decrypt(nonce, body, aad).decode("utf-8")
    except InvalidTag as exc:
        raise DecryptionFailed("ciphertext failed authentication") from exc


def conversation_aad(conversation_id: object) -> bytes:
    """The additional-authenticated-data binding for message content."""
    return f"conversation:{conversation_id}".encode()
