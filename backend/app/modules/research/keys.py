"""Chooses the key wrapper for the running environment (SEC-001 §15, §16).

Kept apart from `crypto`, which stays free of configuration so it can be
tested on its own. The only real decision here is fail-closed: a deployment
that is not development must not quietly fall back to the development
wrapping key, in the same spirit as `CookiePolicy.for_environment`.
"""

from __future__ import annotations

import base64
import binascii
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.modules.research.crypto import (
    DEK_BYTES,
    DecryptionFailed,
    KeyWrapper,
    LocalKeyWrapper,
)

#: Environments permitted to wrap with a locally held key.
_LOCAL_OK = frozenset({"development", "test", "ci"})

#: The shipped default. Recognised explicitly so it can be refused in
#: production even if someone copies it into an environment variable.
_DEV_DEFAULT = "ZGV2LW9ubHktbWFzdGVyLWtleS0zMi1ieXRlcyEhISE="


class KeyConfigurationError(RuntimeError):
    """The key configuration is unusable, or unsafe for this environment."""


class CloudKmsKeyWrapper:
    """Wraps DEKs with Cloud KMS.

    The google-cloud-kms client is imported lazily so that local development
    and CI — which never reach KMS — do not carry the dependency. Add
    `google-cloud-kms` to the project dependencies before deploying with
    `kms_key_name` set.

    Note that KMS never sees research content: it wraps and unwraps 32-byte
    data keys only, which is what keeps "key-use permission separate from
    ciphertext access" (SEC-001 §15) true.
    """

    def __init__(self, key_name: str) -> None:
        try:
            from google.cloud import kms  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - deployment-time path
            raise KeyConfigurationError(
                "kms_key_name is set but google-cloud-kms is not installed; "
                "add it to the project dependencies"
            ) from exc
        self._client = kms.KeyManagementServiceClient()
        self._key_name = key_name

    @property
    def key_name(self) -> str:
        return self._key_name

    def wrap(self, dek: bytes) -> bytes:  # pragma: no cover - needs real KMS
        return bytes(
            self._client.encrypt(
                request={"name": self._key_name, "plaintext": dek}
            ).ciphertext
        )

    def unwrap(self, wrapped: bytes) -> bytes:  # pragma: no cover - needs real KMS
        try:
            return bytes(
                self._client.decrypt(
                    request={"name": self._key_name, "ciphertext": wrapped}
                ).plaintext
            )
        except Exception as exc:
            raise DecryptionFailed("KMS refused to unwrap the data key") from exc


def build_key_wrapper(settings: Settings | None = None) -> KeyWrapper:
    """The wrapper this deployment should use.

    Cloud KMS when a key name is configured; otherwise a locally held key,
    which is permitted only in development, test and CI.
    """
    cfg = settings or get_settings()

    if cfg.kms_key_name:
        return CloudKmsKeyWrapper(cfg.kms_key_name)

    environment = cfg.environment.strip().lower()
    if environment not in _LOCAL_OK:
        raise KeyConfigurationError(
            f"environment {cfg.environment!r} must wrap data keys with KMS: "
            "set kms_key_name"
        )
    if cfg.content_master_key == _DEV_DEFAULT and environment != "development":
        raise KeyConfigurationError(
            "refusing to use the shipped development master key in "
            f"environment {cfg.environment!r}"
        )

    try:
        raw = base64.b64decode(cfg.content_master_key, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise KeyConfigurationError(
            "content_master_key must be valid base64"
        ) from exc
    if len(raw) != DEK_BYTES:
        raise KeyConfigurationError(
            f"content_master_key must decode to {DEK_BYTES} bytes, got {len(raw)}"
        )
    return LocalKeyWrapper(raw, key_name=f"local/{environment}")


@lru_cache
def get_key_wrapper() -> KeyWrapper:
    """Process-wide wrapper. Building a KMS client per request would add a
    connection setup to every message write."""
    return build_key_wrapper()
