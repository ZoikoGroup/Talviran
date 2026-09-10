from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_id_is_echoed() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz", headers={"X-Request-Id": "test-123"})
    assert response.headers["x-request-id"] == "test-123"


def test_unknown_route_returns_canonical_envelope() -> None:
    client = TestClient(create_app())
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "request_id" in body["error"]
