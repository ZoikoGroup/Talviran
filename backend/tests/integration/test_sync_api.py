"""Tests proving app/modules/api/v1/sync.py never serves fabricated price
data in production (2026-11-10 UAT gap analysis G06/G11 remediation):
POST /sync/trigger's hardcoded AMFI/Twelve Data sample rows, and the
/sync/ws websocket's random-walk tick loop, must both be suppressed once
`_is_production()` is true, and everything simulated must carry an explicit
`simulated: true` marker outside production so no consumer can mistake it
for real market data.

Uses fastapi.testclient.TestClient (not the httpx.AsyncClient/ASGITransport
pattern the rest of this suite prefers - see test_reference_api.py's
docstring) because httpx has no websocket support; it is safe here
specifically because this router touches no `db_session` fixture (no
dependency on a DB session at all), so TestClient's own anyio portal can't
hand an asyncpg connection to two event loops the way it could for a
DB-backed endpoint.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.modules.api.v1 import sync as sync_module


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def test_trigger_sync_omits_fabricated_rows_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_module, "_is_production", lambda: True)

    response = client.post("/api/v1/sync/trigger", json={"provider": "all"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["simulated"] is False
    symbols = {a["symbol"] for a in body["assets"]}
    assert "ARM" not in symbols
    assert "HDFCBAL:IN" not in symbols


def test_trigger_sync_flags_simulated_rows_outside_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_module, "_is_production", lambda: False)

    response = client.post("/api/v1/sync/trigger", json={"provider": "all"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["simulated"] is True
    symbols = {a["symbol"] for a in body["assets"]}
    assert "ARM" in symbols


def test_websocket_refuses_simulated_ticks_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_module, "_is_production", lambda: True)

    with client.websocket_connect("/api/v1/sync/ws") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "UNAVAILABLE"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_websocket_marks_ticks_simulated_outside_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_module, "_is_production", lambda: False)

    with client.websocket_connect("/api/v1/sync/ws") as ws:
        init_frame = ws.receive_json()
        assert init_frame["type"] == "INIT"
        assert init_frame["simulated"] is True

        tick_frame = ws.receive_json()
        assert tick_frame["type"] == "TICK"
        assert tick_frame["simulated"] is True
