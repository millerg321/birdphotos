from uuid import uuid4

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


def test_backfill_and_group_requires_internal_token() -> None:
    response = client.post("/jobs/backfill-and-group")
    assert response.status_code == 401


def test_merge_groups_requires_internal_token() -> None:
    response = client.post(
        "/jobs/merge-groups",
        json={"into_group_id": str(uuid4()), "from_group_id": str(uuid4())},
    )
    assert response.status_code == 401
