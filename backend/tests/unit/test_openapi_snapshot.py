import json
from pathlib import Path

from app.main import create_app

OPENAPI_PATH = Path(__file__).resolve().parent.parent.parent / "openapi.json"


def test_openapi_schema_matches_committed_snapshot() -> None:
    current = create_app().openapi()
    committed = json.loads(OPENAPI_PATH.read_text())
    assert current == committed, (
        "openapi.json is stale — run `uv run python -m scripts.export_openapi` "
        "and commit the result."
    )
