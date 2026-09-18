"""Wires up a real backend for market.SourceArtifact.storage_ref — plain
local disk, content-addressed by sha256, not S3 (ENG-ARCH-003 names
S3-compatible object storage as the eventual production target;
SourceArtifact's own docstring has flagged this as "not wired up yet"
since P1 week 8). Swappable later behind this same two-function interface
without touching any caller — every caller already treats storage_ref as
an opaque string, never a raw filesystem path.

Content-addressing means save() is naturally idempotent: re-saving
byte-identical content is a no-op, and a `storage_ref` is only ever
meaningful together with the sha256 the DB row already carries — this
module never re-derives or trusts a hash from the filename alone without
that DB row's corroboration.
"""

from pathlib import Path

from app.core.config import get_settings

_SCHEME = "local-fs://"


def _root() -> Path:
    root = Path(get_settings().artifact_storage_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save(sha256: str, content: bytes) -> str:
    path = _root() / sha256
    if not path.exists():
        path.write_bytes(content)
    return f"{_SCHEME}{sha256}"


def load(storage_ref: str) -> bytes:
    if not storage_ref.startswith(_SCHEME):
        raise ValueError(f"unsupported storage_ref scheme: {storage_ref!r}")
    sha256 = storage_ref.removeprefix(_SCHEME)
    path = _root() / sha256
    return path.read_bytes()
