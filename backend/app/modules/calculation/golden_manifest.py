"""Golden-corpus manifest handling, shared by every calc spec's golden-test
module - FIN-001's Week 12 corpus-integrity check, generalized so it reads
a recorded manifest instead of each golden-test module hand-copying a
SHA256 hex string into its own Python constant.

That hand-copied-constant pattern (see
tests/golden/test_gilt_price_yield_v1_golden.py's original
_CORPUS_V1_SHA256) has exactly the failure mode FIN-001 is designed
against: if corpus.json changes and the test starts failing, the
easiest available fix is to paste in the new hash and move on - which
silently rewrites the golden version's history instead of proposing a new
one. A manifest.json living next to each golden/vN/corpus.json (written
once, by scripts/propose_golden_corpus_version.py, never hand-edited)
removes the temptation: there is no Python constant to "just update."

manifest.json shape:
    {"version": "v1", "sha256": "...", "reason": "...", "created_at": "..."}
"""

import hashlib
import json
from pathlib import Path
from typing import Any


class CorpusIntegrityError(Exception):
    pass


def load_manifest(corpus_dir: Path) -> dict[str, Any]:
    manifest_path = corpus_dir / "manifest.json"
    if not manifest_path.exists():
        raise CorpusIntegrityError(
            f"no manifest.json in {corpus_dir} - every golden corpus version must be "
            "created via scripts.propose_golden_corpus_version, which records one"
        )
    manifest: dict[str, Any] = json.loads(manifest_path.read_text())
    return manifest


def verify_corpus_integrity(corpus_dir: Path) -> dict[str, Any]:
    """Raises CorpusIntegrityError unless corpus.json's current bytes match
    the checksum recorded in this directory's manifest.json. Returns the
    manifest on success, so callers can also assert on its recorded reason.
    """
    manifest = load_manifest(corpus_dir)
    corpus_path = corpus_dir / "corpus.json"
    actual = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    recorded = manifest["sha256"]
    if actual != recorded:
        raise CorpusIntegrityError(
            f"{corpus_path} has changed since {manifest['version']} was finalized "
            f"(manifest sha256={recorded}, actual={actual}). If this is a deliberate "
            "correction, don't edit manifest.json to match - propose a new golden "
            "version instead (scripts.propose_golden_corpus_version), so this "
            "version's history is never silently rewritten."
        )
    return manifest
