"""Regenerates backend/openapi.json from the live FastAPI app. Run after
any change to routes/schemas:

    uv run python -m scripts.export_openapi

tests/unit/test_openapi_snapshot.py regenerates the schema and diffs it
against this committed file on every test run, failing the build on
drift (API-001's "single source of truth for the API contract, CI blocks
undocumented drift" requirement) — the snapshot is generated output, never
hand-edited.
"""

import json
from pathlib import Path

from app.main import create_app

OPENAPI_PATH = Path(__file__).resolve().parent.parent / "openapi.json"


def export() -> None:
    app = create_app()
    schema = app.openapi()
    OPENAPI_PATH.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OPENAPI_PATH}")


if __name__ == "__main__":
    export()
