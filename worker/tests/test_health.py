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


def test_remove_photo_from_group_requires_internal_token() -> None:
    response = client.post(
        "/jobs/remove-photo-from-group", json={"photo_id": str(uuid4())}
    )
    assert response.status_code == 401


def test_delete_photo_requires_internal_token() -> None:
    response = client.post("/jobs/delete-photo", json={"photo_id": str(uuid4())})
    assert response.status_code == 401


def test_delete_group_requires_internal_token() -> None:
    response = client.post("/jobs/delete-group", json={"group_id": str(uuid4())})
    assert response.status_code == 401


def test_set_group_location_requires_internal_token() -> None:
    response = client.post(
        "/jobs/set-group-location",
        json={"group_id": str(uuid4()), "place_name": "London, UK"},
    )
    assert response.status_code == 401
