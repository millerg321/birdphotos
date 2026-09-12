from sqlalchemy.orm import Session

from app.locations import get_or_create_location


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
