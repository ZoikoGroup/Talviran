"""Proves scripts.propose_golden_corpus_version.propose()'s versioning
logic: each call must create the next golden/vN/ directory (never
overwrite one), copy the corpus verbatim, and record a manifest with the
checksum and the given reason.
"""

import hashlib
import json
from pathlib import Path

import pytest

import scripts.propose_golden_corpus_version as propose_module
from scripts.propose_golden_corpus_version import propose


@pytest.fixture(autouse=True)
def _specs_root_in_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    specs_root = tmp_path / "specs"
    (specs_root / "gilt_price_yield_v1").mkdir(parents=True)
    monkeypatch.setattr(propose_module, "_SPECS_ROOT", specs_root)
    return specs_root


def _write_source_corpus(tmp_path: Path, *, name: str = "source.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"cases": [{"id": "case-1"}]}))
    return path


def test_first_proposal_creates_v1(tmp_path: Path, _specs_root_in_tmp_path: Path) -> None:
    source = _write_source_corpus(tmp_path)

    exit_code = propose("gilt_price_yield_v1", source, "initial corpus")

    assert exit_code == 0
    v1_dir = _specs_root_in_tmp_path / "gilt_price_yield_v1" / "golden" / "v1"
    assert (v1_dir / "corpus.json").read_bytes() == source.read_bytes()

    manifest = json.loads((v1_dir / "manifest.json").read_text())
    assert manifest["version"] == "v1"
    assert manifest["reason"] == "initial corpus"
    assert manifest["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_second_proposal_creates_v2_without_touching_v1(
    tmp_path: Path, _specs_root_in_tmp_path: Path
) -> None:
    first_source = _write_source_corpus(tmp_path, name="first.json")
    propose("gilt_price_yield_v1", first_source, "initial corpus")

    v1_dir = _specs_root_in_tmp_path / "gilt_price_yield_v1" / "golden" / "v1"
    v1_bytes_before = (v1_dir / "corpus.json").read_bytes()

    second_source = _write_source_corpus(tmp_path, name="second.json")
    exit_code = propose("gilt_price_yield_v1", second_source, "added boundary cases")

    assert exit_code == 0
    v2_dir = _specs_root_in_tmp_path / "gilt_price_yield_v1" / "golden" / "v2"
    assert (v2_dir / "corpus.json").read_bytes() == second_source.read_bytes()

    assert (v1_dir / "corpus.json").read_bytes() == v1_bytes_before, (
        "proposing v2 must never touch v1's files"
    )
    v1_manifest = json.loads((v1_dir / "manifest.json").read_text())
    assert v1_manifest["reason"] == "initial corpus"


def test_unknown_spec_code_is_refused(tmp_path: Path) -> None:
    source = _write_source_corpus(tmp_path)
    exit_code = propose("no_such_spec", source, "reason")
    assert exit_code == 1


def test_invalid_json_source_is_refused(tmp_path: Path, _specs_root_in_tmp_path: Path) -> None:
    bad_source = tmp_path / "bad.json"
    bad_source.write_text("{not valid json")

    exit_code = propose("gilt_price_yield_v1", bad_source, "reason")

    assert exit_code == 1
    golden_dir = _specs_root_in_tmp_path / "gilt_price_yield_v1" / "golden"
    assert not golden_dir.exists()


def test_missing_source_file_is_refused(tmp_path: Path, _specs_root_in_tmp_path: Path) -> None:
    exit_code = propose("gilt_price_yield_v1", tmp_path / "does_not_exist.json", "reason")
    assert exit_code == 1
