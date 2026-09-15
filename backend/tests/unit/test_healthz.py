"""Uses httpx.AsyncClient with ASGITransport, not fastapi.testclient.TestClient
— see test_reference_api.py's docstring for why TestClient is avoided
throughout this suite (it drives the app through its own anyio portal, a
second event loop, which is a problem for async tests in general even though
these four don't touch the database).
"""

import httpx

from app.main import create_app


async def test_healthz_returns_ok() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_request_id_is_echoed() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz", headers={"X-Request-Id": "test-123"})
    assert response.headers["x-request-id"] == "test-123"


def test_pack_registry_is_wired_into_app_state() -> None:
    app = create_app()
    assert app.state.pack_registry.get("uk-gilts") is not None


async def test_unknown_route_returns_canonical_envelope() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "request_id" in body["error"]
