import uuid

from sqlalchemy.orm import Session

from app.config import settings
from app.models import BurstGroup, BurstGroupSpecies, Photo
from app.queries import effective_best_shot_photo_id, get_effective_species


def _make_group_with_photo(db: Session) -> BurstGroup:
    group = BurstGroup()
    db.add(group)
    db.flush()

    photo = Photo(
        burst_group_id=group.id,
        r2_key_original="o",
        r2_key_thumb="t",
        r2_key_medium="m",
        taken_at="2026-01-01T00:00:00",
    )
    db.add(photo)
    db.flush()
    return group


def test_confirmed_always_wins_over_pending(db: Session) -> None:
    group = _make_group_with_photo(db)
    db.add_all(
        [
            BurstGroupSpecies(
                burst_group_id=group.id,
                source="ai_suggested",
                status="pending_review",
                confidence=0.99,
            ),
            BurstGroupSpecies(
                burst_group_id=group.id,
                source="manual",
                status="confirmed",
                confidence=None,
            ),
        ]
    )
    db.flush()

    result = get_effective_species(db, group.id)
    assert result is not None
    assert result.status == "confirmed"


def test_pending_ignored_when_ai_not_trusted(db: Session, monkeypatch) -> None:
    settings.trust_ai_suggestions = False
    group = _make_group_with_photo(db)
    db.add(
        BurstGroupSpecies(
            burst_group_id=group.id,
            source="ai_suggested",
            status="pending_review",
            confidence=0.9,
        )
    )
    db.flush()

    assert get_effective_species(db, group.id) is None


def test_pending_used_when_ai_trusted(db: Session) -> None:
    settings.trust_ai_suggestions = True
    try:
        group = _make_group_with_photo(db)
        db.add(
            BurstGroupSpecies(
                burst_group_id=group.id,
                source="ai_suggested",
                status="pending_review",
                confidence=0.9,
            )
        )
        db.flush()

        result = get_effective_species(db, group.id)
        assert result is not None
        assert result.status == "pending_review"
    finally:
        settings.trust_ai_suggestions = False


def test_override_takes_precedence_over_computed_best_shot() -> None:
    computed_id = uuid.uuid4()
    override_id = uuid.uuid4()
    group = BurstGroup(best_shot_photo_id=computed_id, best_shot_override_photo_id=override_id)
    assert effective_best_shot_photo_id(group) == override_id


def test_computed_best_shot_used_when_no_override() -> None:
    computed_id = uuid.uuid4()
    group = BurstGroup(best_shot_photo_id=computed_id, best_shot_override_photo_id=None)
    assert effective_best_shot_photo_id(group) == computed_id
