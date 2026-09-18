"""Unit tests for golden_manifest.py - the shared corpus-integrity check
every calc spec's golden-test module uses instead of a hand-copied SHA256
constant.
"""

import hashlib
import json
from pathlib import Path

import pytest

from app.modules.calculation.golden_manifest import CorpusIntegrityError, verify_corpus_integrity


def _write_corpus_and_manifest(
    tmp_path: Path, *, corpus_bytes: bytes, sha256: str, reason: str = "test"
) -> Path:
    corpus_dir = tmp_path / "v1"
    corpus_dir.mkdir()
    (corpus_dir / "corpus.json").write_bytes(corpus_bytes)
    (corpus_dir / "manifest.json").write_text(
        json.dumps({"version": "v1", "sha256": sha256, "reason": reason, "created_at": "now"})
    )
    return corpus_dir


def test_matching_checksum_passes_and_returns_the_manifest(tmp_path: Path) -> None:
    corpus_bytes = b'{"cases": []}'
    sha256 = hashlib.sha256(corpus_bytes).hexdigest()
    corpus_dir = _write_corpus_and_manifest(
        tmp_path, corpus_bytes=corpus_bytes, sha256=sha256, reason="initial version"
    )

    manifest = verify_corpus_integrity(corpus_dir)

    assert manifest["reason"] == "initial version"
    assert manifest["sha256"] == sha256


def test_changed_corpus_bytes_raise_not_silently_pass(tmp_path: Path) -> None:
    original_bytes = b'{"cases": []}'
    stale_sha256 = hashlib.sha256(original_bytes).hexdigest()
    corpus_dir = _write_corpus_and_manifest(
        tmp_path, corpus_bytes=original_bytes, sha256=stale_sha256
    )

    (corpus_dir / "corpus.json").write_bytes(b'{"cases": [{"id": "snuck-in"}]}')

    with pytest.raises(CorpusIntegrityError, match="propose a new golden version"):
        verify_corpus_integrity(corpus_dir)


def test_missing_manifest_raises_not_silently_skips(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "v1"
    corpus_dir.mkdir()
    (corpus_dir / "corpus.json").write_bytes(b"{}")

    with pytest.raises(CorpusIntegrityError, match="no manifest.json"):
        verify_corpus_integrity(corpus_dir)
