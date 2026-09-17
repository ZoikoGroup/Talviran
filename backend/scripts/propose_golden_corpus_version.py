"""P2's golden-harness tooling: proposes a new, immutable golden-corpus
version for a calc spec - the "recorded governance sign-off" companion to
scripts/approve_calculation_spec.py (which runs an *existing* version's
tests; this is what creates a new version in the first place).

Never overwrites an existing golden/vN/ directory - each call creates the
next version number, copies the given corpus JSON into it verbatim, and
writes a manifest.json recording its checksum and the reason for the new
version. That reason is the sign-off record: why this corpus exists, not
just that it does (calculation/models.py's CalculationSupersession
docstring makes the same distinction for calculation results).

This does NOT write any test module against the new corpus, and does NOT
approve anything - a human still writes tests/golden/test_<spec>_golden.py
against the new version and registers it in
scripts/approve_calculation_spec.py's _GOLDEN_TEST_PATHS, same as today.
What this removes is the hand-copied-checksum step that invites silently
rewriting a prior version's history instead of adding a new one.

Run with:

    uv run python -m scripts.propose_golden_corpus_version \\
        gilt_price_yield_v1 path/to/new_corpus.json \\
        --reason "Added 4 boundary cases for leap-year settlement dates"
"""

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

_SPECS_ROOT = Path(__file__).resolve().parent.parent / "app" / "modules" / "calculation" / "specs"
_VERSION_DIR_PATTERN = re.compile(r"^v(\d+)$")


def _next_version_number(golden_dir: Path) -> int:
    if not golden_dir.exists():
        return 1
    existing = [
        int(m.group(1))
        for entry in golden_dir.iterdir()
        if entry.is_dir() and (m := _VERSION_DIR_PATTERN.match(entry.name))
    ]
    return max(existing, default=0) + 1


def propose(spec_code: str, source_corpus_path: Path, reason: str) -> int:
    spec_dir = _SPECS_ROOT / spec_code
    if not spec_dir.is_dir():
        print(f"No spec directory for {spec_code!r} at {spec_dir}.")
        return 1

    if not source_corpus_path.is_file():
        print(f"Source corpus file not found: {source_corpus_path}")
        return 1

    try:
        corpus_bytes = source_corpus_path.read_bytes()
        json.loads(corpus_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Source corpus is not valid JSON: {exc}")
        return 1

    golden_dir = spec_dir / "golden"
    version_number = _next_version_number(golden_dir)
    version_name = f"v{version_number}"
    version_dir = golden_dir / version_name
    version_dir.mkdir(parents=True, exist_ok=False)

    corpus_path = version_dir / "corpus.json"
    corpus_path.write_bytes(corpus_bytes)

    sha256 = hashlib.sha256(corpus_bytes).hexdigest()
    manifest = {
        "version": version_name,
        "sha256": sha256,
        "reason": reason,
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    (version_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Proposed {spec_code} golden/{version_name}/ (sha256={sha256}).")
    print(f"Reason recorded: {reason}")
    print(
        "\nNext steps (this script does not do these):\n"
        f"  1. Write tests/golden/test_{spec_code}_golden.py cases against golden/{version_name}/\n"
        f"  2. Register {spec_code} in scripts/approve_calculation_spec.py's _GOLDEN_TEST_PATHS\n"
        "     if not already present (only needed once per spec code)\n"
        "  3. Run scripts.approve_calculation_spec to move the spec to APPROVED"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec_code", help="e.g. gilt_price_yield_v1")
    parser.add_argument("source_corpus_path", type=Path, help="path to the new corpus JSON file")
    parser.add_argument("--reason", required=True, help="why this new version exists")
    args = parser.parse_args()
    sys.exit(propose(args.spec_code, args.source_corpus_path, args.reason))


if __name__ == "__main__":
    main()
