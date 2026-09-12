import io
import uuid
from datetime import datetime

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.group_bursts import (
    backfill_scores,
    delete_group,
    delete_photo,
    merge_groups,
    regroup_all,
    remove_photo_from_group,
)
from app.models import BurstGroup, BurstGroupSpecies, BurstGroupTag, Photo, Tag


def _jpeg(value: int) -> bytes:
    arr = np.full((100, 100, 3), value, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG")
    return buf.getvalue()


def _make_photo(db: Session, taken_at: datetime, r2_key: str) -> Photo:
    group = BurstGroup()
    db.add(group)
    db.flush()
    photo = Photo(
        burst_group_id=group.id,
        r2_key_original=r2_key,
        r2_key_thumb=f"{r2_key}-thumb",
        r2_key_medium=f"{r2_key}-medium",
        taken_at=taken_at,
        import_status="processed",
    )
    db.add(photo)
    db.flush()
    return photo


def _make_merged_group(
    db: Session, taken_ats: list[datetime], r2_keys: list[str], *, scored: bool = True
) -> BurstGroup:
    """A locked multi-photo group, as merge_groups would leave one —
    built directly rather than via merge_groups so these tests don't
    couple to its behavior."""
    group = BurstGroup()
    db.add(group)
    db.flush()
    photos = []
    for taken_at, r2_key in zip(taken_ats, r2_keys, strict=True):
        photo = Photo(
            burst_group_id=group.id,
            r2_key_original=r2_key,
            r2_key_thumb=f"{r2_key}-thumb",
            r2_key_medium=f"{r2_key}-medium",
            taken_at=taken_at,
            import_status="processed",
            grouping_locked=True,
        )
        if scored:
            photo.phash = "0" * 16
            photo.sharpness_score = 1.0
            photo.exposure_score = 1.0
        db.add(photo)
        photos.append(photo)
    db.flush()
    group.best_shot_photo_id = photos[0].id
    db.flush()
    return group


@pytest.fixture
def fake_r2(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """In-memory stand-in for R2, keyed by r2_key_original — a plain
    monkeypatch rather than moto, since the surface being exercised here
    is just get/put by key, not real S3 semantics."""
    store: dict[str, bytes] = {}
    monkeypatch.setattr(
        "app.jobs.group_bursts.download_bytes", lambda key: store[key]
    )
    return store


class TestBackfillScores:
    def test_populates_missing_scores(self, db: Session, fake_r2: dict[str, bytes]) -> None:
        fake_r2["a"] = _jpeg(128)
        photo = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")

        count = backfill_scores(db)

        db.refresh(photo)
        assert count == 1
        assert photo.phash is not None
        assert photo.sharpness_score is not None
        assert photo.exposure_score is not None

    def test_skips_already_scored_photos(self, db: Session, fake_r2: dict[str, bytes]) -> None:
        fake_r2["a"] = _jpeg(128)
        _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        backfill_scores(db)

        # Removing "a" from the fake store proves a second run doesn't
        # try to re-download it.
        del fake_r2["a"]
        count = backfill_scores(db)
        assert count == 0


class TestRegroupAll:
    def test_merges_similar_photos_close_in_time(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        fake_r2["a"] = _jpeg(128)
        fake_r2["b"] = _jpeg(128)  # identical image -> phash distance 0
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 1), "b")
        backfill_scores(db)

        regroup_all(db)

        db.refresh(photo_a)
        db.refresh(photo_b)
        assert photo_a.burst_group_id == photo_b.burst_group_id

    def test_keeps_distant_photos_in_separate_groups(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        fake_r2["a"] = _jpeg(0)
        fake_r2["b"] = _jpeg(255)
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 13, 0, 0), "b")
        backfill_scores(db)

        regroup_all(db)

        db.refresh(photo_a)
        db.refresh(photo_b)
        assert photo_a.burst_group_id != photo_b.burst_group_id

    def test_deletes_the_orphaned_group_after_a_merge(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        fake_r2["a"] = _jpeg(128)
        fake_r2["b"] = _jpeg(128)
        _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 1), "b")
        original_group_b_id = photo_b.burst_group_id
        backfill_scores(db)

        regroup_all(db)

        assert db.get(BurstGroup, original_group_b_id) is None

    def test_ignores_manually_grouping_locked_photos(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        """A manual merge (grouping_locked=True) must survive a later
        regroup_all — otherwise the whole-library rescan would silently
        undo it, since it has no other concept of a manual override."""
        fake_r2["a"] = _jpeg(128)
        fake_r2["b"] = _jpeg(128)  # identical -> would normally merge
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 1), "b")
        original_group_a_id = photo_a.burst_group_id
        original_group_b_id = photo_b.burst_group_id
        backfill_scores(db)
        photo_a.grouping_locked = True
        photo_b.grouping_locked = True
        db.flush()

        regroup_all(db)

        db.refresh(photo_a)
        db.refresh(photo_b)
        assert photo_a.burst_group_id == original_group_a_id
        assert photo_b.burst_group_id == original_group_b_id
        assert db.get(BurstGroup, original_group_a_id) is not None
        assert db.get(BurstGroup, original_group_b_id) is not None


class TestMergeGroups:
    def test_moves_photos_into_the_target_group(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        fake_r2["a"] = _jpeg(128)
        fake_r2["b"] = _jpeg(200)
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 40), "b")
        backfill_scores(db)

        merge_groups(db, into_group_id=photo_a.burst_group_id, from_group_id=photo_b.burst_group_id)

        db.refresh(photo_b)
        assert photo_b.burst_group_id == photo_a.burst_group_id

    def test_deletes_the_emptied_source_group(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        fake_r2["a"] = _jpeg(128)
        fake_r2["b"] = _jpeg(200)
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 40), "b")
        from_group_id = photo_b.burst_group_id
        backfill_scores(db)

        merge_groups(db, into_group_id=photo_a.burst_group_id, from_group_id=from_group_id)

        assert db.get(BurstGroup, from_group_id) is None

    def test_locks_every_photo_in_the_merged_group(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        fake_r2["a"] = _jpeg(128)
        fake_r2["b"] = _jpeg(200)
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 40), "b")
        backfill_scores(db)

        merge_groups(db, into_group_id=photo_a.burst_group_id, from_group_id=photo_b.burst_group_id)

        db.refresh(photo_a)
        db.refresh(photo_b)
        assert photo_a.grouping_locked is True
        assert photo_b.grouping_locked is True

    def test_recomputes_best_shot_across_all_merged_photos(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        fake_r2["a"] = _jpeg(0)  # flat/dark -> low sharpness
        fake_r2["b"] = _jpeg(128)
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 40), "b")
        backfill_scores(db)

        merge_groups(db, into_group_id=photo_a.burst_group_id, from_group_id=photo_b.burst_group_id)

        group = db.get(BurstGroup, photo_a.burst_group_id)
        assert group is not None
        assert group.best_shot_photo_id in {photo_a.id, photo_b.id}

    def test_leaves_best_shot_unchanged_when_photos_are_unscored(
        self, db: Session
    ) -> None:
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 40), "b")
        # No backfill_scores() call — both photos are unscored.

        merge_groups(db, into_group_id=photo_a.burst_group_id, from_group_id=photo_b.burst_group_id)

        group = db.get(BurstGroup, photo_a.burst_group_id)
        assert group is not None
        assert group.best_shot_photo_id is None

    def test_rejects_merging_a_group_with_itself(self, db: Session) -> None:
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        with pytest.raises(ValueError):
            merge_groups(
                db, into_group_id=photo_a.burst_group_id, from_group_id=photo_a.burst_group_id
            )

    def test_an_empty_source_group_is_a_no_op(self, db: Session) -> None:
        """Not an error case: this is what a duplicate merge submission
        (e.g. a double-click) looks like on its second, redundant call —
        see the real 500 this caused in production before this fix."""
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        empty_group = BurstGroup()
        db.add(empty_group)
        db.flush()

        result = merge_groups(
            db, into_group_id=photo_a.burst_group_id, from_group_id=empty_group.id
        )

        assert result == photo_a.burst_group_id

    def test_a_repeated_merge_of_the_same_pair_does_not_error(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        """The exact production failure: the same merge submitted twice
        in quick succession. The first call does the real work; the
        second must be a harmless no-op, not a 500."""
        fake_r2["a"] = _jpeg(128)
        fake_r2["b"] = _jpeg(200)
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 40), "b")
        into_group_id, from_group_id = photo_a.burst_group_id, photo_b.burst_group_id
        backfill_scores(db)

        merge_groups(db, into_group_id=into_group_id, from_group_id=from_group_id)
        result = merge_groups(db, into_group_id=into_group_id, from_group_id=from_group_id)

        assert result == into_group_id

    def test_reassigns_species_candidates_from_the_deleted_group(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        fake_r2["a"] = _jpeg(128)
        fake_r2["b"] = _jpeg(200)
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 40), "b")
        candidate = BurstGroupSpecies(
            burst_group_id=photo_b.burst_group_id, source="ai_suggested"
        )
        db.add(candidate)
        db.flush()
        backfill_scores(db)

        merge_groups(db, into_group_id=photo_a.burst_group_id, from_group_id=photo_b.burst_group_id)

        db.refresh(candidate)
        assert candidate.burst_group_id == photo_a.burst_group_id

    def test_reassigns_tags_from_the_deleted_group(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        fake_r2["a"] = _jpeg(128)
        fake_r2["b"] = _jpeg(200)
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 40), "b")
        tag = Tag(name="favorite", slug="favorite")
        db.add(tag)
        db.flush()
        db.add(BurstGroupTag(burst_group_id=photo_b.burst_group_id, tag_id=tag.id))
        db.flush()
        backfill_scores(db)

        merge_groups(db, into_group_id=photo_a.burst_group_id, from_group_id=photo_b.burst_group_id)

        remaining = db.execute(
            select(BurstGroupTag).where(BurstGroupTag.burst_group_id == photo_a.burst_group_id)
        ).scalars().all()
        assert [t.tag_id for t in remaining] == [tag.id]

    def test_dedupes_a_tag_shared_by_both_groups(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        fake_r2["a"] = _jpeg(128)
        fake_r2["b"] = _jpeg(200)
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 40), "b")
        tag = Tag(name="favorite", slug="favorite")
        db.add(tag)
        db.flush()
        db.add(BurstGroupTag(burst_group_id=photo_a.burst_group_id, tag_id=tag.id))
        db.add(BurstGroupTag(burst_group_id=photo_b.burst_group_id, tag_id=tag.id))
        db.flush()
        backfill_scores(db)

        # Would violate the (burst_group_id, tag_id) composite PK if the
        # from-group's row were reassigned instead of deduped away.
        merge_groups(db, into_group_id=photo_a.burst_group_id, from_group_id=photo_b.burst_group_id)

        remaining = db.execute(
            select(BurstGroupTag).where(BurstGroupTag.burst_group_id == photo_a.burst_group_id)
        ).scalars().all()
        assert [t.tag_id for t in remaining] == [tag.id]

    def test_merge_survives_a_later_regroup_all(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        """The actual point of grouping_locked: without it, this merge
        would get silently undone the next time someone clicks "Score &
        group new photos"."""
        fake_r2["a"] = _jpeg(0)
        fake_r2["b"] = _jpeg(255)  # maximally different -> would never
        # auto-merge with "a" on its own
        photo_a = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_b = _make_photo(db, datetime(2024, 1, 1, 12, 0, 1), "b")
        backfill_scores(db)

        merge_groups(db, into_group_id=photo_a.burst_group_id, from_group_id=photo_b.burst_group_id)
        regroup_all(db)

        db.refresh(photo_a)
        db.refresh(photo_b)
        assert photo_a.burst_group_id == photo_b.burst_group_id


class TestRemovePhotoFromGroup:
    def test_creates_a_new_unlocked_singleton_group(self, db: Session) -> None:
        group = _make_merged_group(
            db,
            [datetime(2024, 1, 1, 12, 0, 0), datetime(2024, 1, 1, 12, 0, 1)],
            ["a", "b"],
        )
        photo_b = db.execute(select(Photo).where(Photo.r2_key_original == "b")).scalar_one()

        new_group_id = remove_photo_from_group(db, photo_b.id)

        db.refresh(photo_b)
        assert photo_b.burst_group_id == new_group_id
        assert photo_b.burst_group_id != group.id
        assert photo_b.grouping_locked is False
        new_group = db.get(BurstGroup, new_group_id)
        assert new_group is not None
        assert new_group.best_shot_photo_id == photo_b.id

    def test_leaves_remaining_photos_locked_and_in_original_group(self, db: Session) -> None:
        group = _make_merged_group(
            db,
            [
                datetime(2024, 1, 1, 12, 0, 0),
                datetime(2024, 1, 1, 12, 0, 1),
                datetime(2024, 1, 1, 12, 0, 2),
            ],
            ["a", "b", "c"],
        )
        photo_c = db.execute(select(Photo).where(Photo.r2_key_original == "c")).scalar_one()

        remove_photo_from_group(db, photo_c.id)

        remaining = db.execute(
            select(Photo).where(Photo.burst_group_id == group.id)
        ).scalars().all()
        assert {p.r2_key_original for p in remaining} == {"a", "b"}
        assert all(p.grouping_locked for p in remaining)

    def test_unlocks_the_last_remaining_photo_when_group_drops_to_one(
        self, db: Session
    ) -> None:
        group = _make_merged_group(
            db,
            [datetime(2024, 1, 1, 12, 0, 0), datetime(2024, 1, 1, 12, 0, 1)],
            ["a", "b"],
        )
        photo_b = db.execute(select(Photo).where(Photo.r2_key_original == "b")).scalar_one()

        remove_photo_from_group(db, photo_b.id)

        photo_a = db.execute(select(Photo).where(Photo.r2_key_original == "a")).scalar_one()
        assert photo_a.burst_group_id == group.id
        assert photo_a.grouping_locked is False

    def test_recomputes_best_shot_for_the_original_group(self, db: Session) -> None:
        group = _make_merged_group(
            db,
            [
                datetime(2024, 1, 1, 12, 0, 0),
                datetime(2024, 1, 1, 12, 0, 1),
                datetime(2024, 1, 1, 12, 0, 2),
            ],
            ["a", "b", "c"],
        )
        photo_a = db.execute(select(Photo).where(Photo.r2_key_original == "a")).scalar_one()
        # "a" was the original best shot (see _make_merged_group) — removing
        # it must leave the group pointing at one of the photos still in it.
        remove_photo_from_group(db, photo_a.id)

        db.refresh(group)
        remaining_ids = {
            p.id
            for p in db.execute(
                select(Photo).where(Photo.burst_group_id == group.id)
            ).scalars()
        }
        assert group.best_shot_photo_id in remaining_ids

    def test_rejects_removing_from_an_already_singleton_group(self, db: Session) -> None:
        photo = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        with pytest.raises(ValueError):
            remove_photo_from_group(db, photo.id)

    def test_rejects_an_unknown_photo(self, db: Session) -> None:
        with pytest.raises(ValueError):
            remove_photo_from_group(db, uuid.uuid4())


class TestDeletePhoto:
    def test_removes_the_photo_row(self, db: Session) -> None:
        photo = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        photo_id = photo.id

        delete_photo(db, photo_id)

        assert db.get(Photo, photo_id) is None

    def test_returns_the_r2_keys(self, db: Session) -> None:
        photo = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")

        outcome = delete_photo(db, photo.id)

        assert set(outcome.r2_keys) == {"a", "a-thumb", "a-medium"}

    def test_deletes_the_group_when_it_was_the_only_photo(self, db: Session) -> None:
        photo = _make_photo(db, datetime(2024, 1, 1, 12, 0, 0), "a")
        group_id = photo.burst_group_id

        outcome = delete_photo(db, photo.id)

        assert db.get(BurstGroup, group_id) is None
        assert outcome.surviving_group_id is None

    def test_recomputes_best_shot_when_others_remain(self, db: Session) -> None:
        group = _make_merged_group(
            db,
            [datetime(2024, 1, 1, 12, 0, 0), datetime(2024, 1, 1, 12, 0, 1)],
            ["a", "b"],
        )
        photo_a = db.execute(select(Photo).where(Photo.r2_key_original == "a")).scalar_one()
        photo_b = db.execute(select(Photo).where(Photo.r2_key_original == "b")).scalar_one()

        outcome = delete_photo(db, photo_a.id)

        db.refresh(group)
        assert group.best_shot_photo_id == photo_b.id
        assert db.get(BurstGroup, group.id) is not None
        assert outcome.surviving_group_id == group.id

    def test_rejects_an_unknown_photo(self, db: Session) -> None:
        with pytest.raises(ValueError):
            delete_photo(db, uuid.uuid4())


class TestDeleteGroup:
    def test_removes_all_photos_and_the_group(self, db: Session) -> None:
        group = _make_merged_group(
            db,
            [datetime(2024, 1, 1, 12, 0, 0), datetime(2024, 1, 1, 12, 0, 1)],
            ["a", "b"],
        )
        photo_ids = [
            p.id
            for p in db.execute(
                select(Photo).where(Photo.burst_group_id == group.id)
            ).scalars()
        ]

        delete_group(db, group.id)

        assert db.get(BurstGroup, group.id) is None
        for photo_id in photo_ids:
            assert db.get(Photo, photo_id) is None

    def test_returns_all_r2_keys(self, db: Session) -> None:
        group = _make_merged_group(
            db,
            [datetime(2024, 1, 1, 12, 0, 0), datetime(2024, 1, 1, 12, 0, 1)],
            ["a", "b"],
        )

        keys = delete_group(db, group.id)

        assert set(keys) == {
            "a", "a-thumb", "a-medium",
            "b", "b-thumb", "b-medium",
        }

    def test_rejects_an_unknown_group(self, db: Session) -> None:
        with pytest.raises(ValueError):
            delete_group(db, uuid.uuid4())
