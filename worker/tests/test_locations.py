from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.locations import geocode_place_name, get_or_create_location, set_group_location
from app.models import BurstGroup, Photo


class TestGetOrCreateLocation:
    def test_creates_new_location(self, db: Session) -> None:
        location = get_or_create_location(db, "Borneo", 1.0, 114.0)
        assert location.name == "Borneo"
        assert location.center_lat == 1.0

    def test_matches_existing_case_insensitively(self, db: Session) -> None:
        first = get_or_create_location(db, "London, UK", 51.5074, -0.1278)
        second = get_or_create_location(db, "london, uk", 51.5074, -0.1278)
        assert first.id == second.id

    def test_different_locations_get_different_rows(self, db: Session) -> None:
        a = get_or_create_location(db, "London, UK", 51.5074, -0.1278)
        b = get_or_create_location(db, "Ireland", 53.1424, -7.6921)
        assert a.id != b.id


def _fake_nominatim_response(results: list[dict[str, str]]) -> MagicMock:
    response = MagicMock()
    response.json.return_value = results
    return response


class TestGeocodePlaceName:
    def test_returns_coordinates_for_a_match(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.locations.httpx.get",
            lambda *a, **kw: _fake_nominatim_response(
                [{"lat": "51.5074", "lon": "-0.1278"}]
            ),
        )

        result = geocode_place_name("London, UK")

        assert result == (51.5074, -0.1278)

    def test_returns_none_when_no_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.locations.httpx.get", lambda *a, **kw: _fake_nominatim_response([])
        )

        assert geocode_place_name("Not A Real Place Xyzzy") is None

    def test_sends_an_identifying_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = {}

        def fake_get(url: str, params: dict, headers: dict, timeout: float) -> MagicMock:
            captured["headers"] = headers
            return _fake_nominatim_response([{"lat": "1.0", "lon": "2.0"}])

        monkeypatch.setattr("app.locations.httpx.get", fake_get)

        geocode_place_name("Somewhere")

        assert "User-Agent" in captured["headers"]
        assert captured["headers"]["User-Agent"] != ""


class TestSetGroupLocation:
    def test_assigns_location_to_every_photo_in_the_group(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        group = BurstGroup()
        db.add(group)
        db.flush()
        photos = [
            Photo(
                burst_group_id=group.id,
                r2_key_original=f"o{i}",
                r2_key_thumb=f"t{i}",
                r2_key_medium=f"m{i}",
                taken_at=datetime(2024, 1, 1, 12, 0, i),
            )
            for i in range(3)
        ]
        db.add_all(photos)
        db.flush()

        monkeypatch.setattr(
            "app.locations.geocode_place_name", lambda place_name: (51.5074, -0.1278)
        )

        location = set_group_location(db, group.id, "London, UK")

        for photo in photos:
            db.refresh(photo)
            assert photo.location_id == location.id

    def test_reuses_an_existing_location_by_name(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        existing = get_or_create_location(db, "London, UK", 51.5074, -0.1278)
        group = BurstGroup()
        db.add(group)
        db.flush()
        photo = Photo(
            burst_group_id=group.id,
            r2_key_original="o",
            r2_key_thumb="t",
            r2_key_medium="m",
            taken_at=datetime(2024, 1, 1),
        )
        db.add(photo)
        db.flush()

        monkeypatch.setattr(
            "app.locations.geocode_place_name", lambda place_name: (51.5074, -0.1278)
        )

        location = set_group_location(db, group.id, "London, UK")

        assert location.id == existing.id

    def test_raises_when_geocoding_finds_nothing(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        group = BurstGroup()
        db.add(group)
        db.flush()

        monkeypatch.setattr("app.locations.geocode_place_name", lambda place_name: None)

        with pytest.raises(ValueError):
            set_group_location(db, group.id, "Not A Real Place Xyzzy")
