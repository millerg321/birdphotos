import io
from datetime import datetime

import numpy as np
import pytest
from PIL import Image
from sqlalchemy.orm import Session

from app.jobs.group_bursts import backfill_scores, regroup_all
from app.models import BurstGroup, Photo


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
