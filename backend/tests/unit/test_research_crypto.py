"""Envelope encryption primitives (SEC-001 §15.1)."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.research import crypto
from app.modules.research.crypto import DEK_BYTES, LocalKeyWrapper
from app.modules.research.keys import KeyConfigurationError, build_key_wrapper

WRAPPER = LocalKeyWrapper(b"\x33" * DEK_BYTES, key_name="test/unit")
DEV_KEY = "ZGV2LW9ubHktbWFzdGVyLWtleS0zMi1ieXRlcyEhISE="


def test_content_round_trips() -> None:
    dek = crypto.new_dek()
    blob = crypto.encrypt(dek, "10y gilt yield")
    assert crypto.decrypt(dek, blob) == "10y gilt yield"


def test_the_ciphertext_does_not_contain_the_plaintext() -> None:
    dek = crypto.new_dek()
    assert b"gilt" not in crypto.encrypt(dek, "gilt")


def test_the_same_text_encrypts_differently_every_time() -> None:
    """A fresh nonce per call. Deterministic ciphertext would let an observer
    tell that two accounts asked the same question."""
    dek = crypto.new_dek()
    assert crypto.encrypt(dek, "same") != crypto.encrypt(dek, "same")


def test_another_key_cannot_decrypt() -> None:
    blob = crypto.encrypt(crypto.new_dek(), "private")
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(crypto.new_dek(), blob)


def test_tampering_is_detected() -> None:
    """GCM authenticates; a flipped byte must fail rather than decode to junk."""
    dek = crypto.new_dek()
    blob = bytearray(crypto.encrypt(dek, "untampered"))
    blob[-1] ^= 0x01
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(dek, bytes(blob))


def test_a_truncated_value_fails_cleanly() -> None:
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(crypto.new_dek(), b"\x00\x01")


def test_aad_binds_the_ciphertext_to_its_conversation() -> None:
    dek = crypto.new_dek()
    blob = crypto.encrypt(dek, "in thread A", aad=crypto.conversation_aad("A"))
    assert crypto.decrypt(dek, blob, aad=crypto.conversation_aad("A")) == "in thread A"
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(dek, blob, aad=crypto.conversation_aad("B"))


def test_the_wrapped_key_is_not_the_key() -> None:
    dek, envelope = crypto.create_envelope(WRAPPER)
    assert dek not in envelope.wrapped_dek
    assert crypto.open_envelope(WRAPPER, envelope) == dek


def test_a_different_wrapper_cannot_unwrap() -> None:
    _, envelope = crypto.create_envelope(WRAPPER)
    other = LocalKeyWrapper(b"\x44" * DEK_BYTES)
    with pytest.raises(crypto.DecryptionFailed):
        crypto.open_envelope(other, envelope)


def test_an_unknown_envelope_version_is_refused() -> None:
    _, envelope = crypto.create_envelope(WRAPPER)
    bumped = crypto.Envelope(
        wrapped_dek=envelope.wrapped_dek, key_name=envelope.key_name, version=99
    )
    with pytest.raises(crypto.DecryptionFailed):
        crypto.open_envelope(WRAPPER, bumped)


def test_a_short_master_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        LocalKeyWrapper(b"too-short")


# ------------------------------------------------------------ fail closed


def test_production_refuses_a_locally_held_key() -> None:
    """A deployment that is not development must wrap with KMS."""
    with pytest.raises(KeyConfigurationError):
        build_key_wrapper(Settings(environment="production", kms_key_name=None))


def test_staging_refuses_the_shipped_development_key() -> None:
    with pytest.raises(KeyConfigurationError):
        build_key_wrapper(
            Settings(environment="staging", content_master_key=DEV_KEY)
        )


def test_development_may_use_a_local_key() -> None:
    wrapper = build_key_wrapper(
        Settings(environment="development", content_master_key=DEV_KEY)
    )
    assert wrapper.key_name == "local/development"


def test_a_malformed_master_key_is_rejected() -> None:
    with pytest.raises(KeyConfigurationError):
        build_key_wrapper(
            Settings(environment="development", content_master_key="not base64!!")
        )
