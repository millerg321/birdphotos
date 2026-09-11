from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_sync_requires_internal_token() -> None:
    response = client.post("/sync/google-photos")
    assert response.status_code == 401
