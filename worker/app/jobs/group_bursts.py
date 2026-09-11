from sqlalchemy import select
from sqlalchemy.orm import Session

from app.grouping import (
    PhotoForGrouping,
    PhotoForScoring,
    group_by_burst,
    select_best_shot,
)
from app.models import BurstGroup, Photo
from app.scoring import compute_exposure, compute_phash, compute_sharpness
from app.storage import download_bytes


def _non_null[T](value: T | None) -> T:
    """Narrows a nullable ORM column value for callers that already
    filtered the query on IS NOT NULL — SQLAlchemy's `.is_not(None)`
    doesn't narrow the mapped attribute's type, so mypy can't see it."""
    assert value is not None
    return value


def backfill_scores(db: Session) -> int:
    """Computes phash/sharpness/exposure for any photo missing them.
    Downloads the original from R2 since scoring needs real pixel data,
    not just the thumbnail (see plan: Burst Detection)."""
    photos = db.execute(
        select(Photo).where(Photo.phash.is_(None))
    ).scalars().all()

    for photo in photos:
        original = download_bytes(photo.r2_key_original)
        photo.phash = compute_phash(original)
        photo.sharpness_score = compute_sharpness(original)
        photo.exposure_score = compute_exposure(original)

    db.flush()
    return len(photos)


def regroup_all(db: Session) -> int:
    """Recomputes burst groups across every scored photo, merging
    existing singleton groups where the grouping algorithm says they
    belong together, and setting best_shot_photo_id per resulting group.

    Whole-table regrouping rather than incremental (only "recently
    imported" photos) is deliberately simple for now — fine at this
    dataset size; revisit if/when Phase 2's ongoing import volume makes
    a full rescan too slow.
    """
    photos = db.execute(
        select(Photo).where(
            Photo.phash.is_not(None),
            Photo.sharpness_score.is_not(None),
            Photo.exposure_score.is_not(None),
        )
    ).scalars().all()
    photos_by_id = {p.id: p for p in photos}

    computed_groups = group_by_burst(
        [
            PhotoForGrouping(id=p.id, taken_at=p.taken_at, phash=_non_null(p.phash))
            for p in photos
        ]
    )

    for photo_ids in computed_groups:
        # The surviving burst_group is whichever the earliest-taken photo
        # in this computed group already belongs to — arbitrary but
        # stable, and avoids creating a fresh group row on every rerun.
        group_photos = sorted(
            (photos_by_id[pid] for pid in photo_ids), key=lambda p: p.taken_at
        )
        surviving_group_id = group_photos[0].burst_group_id
        other_group_ids = {
            p.burst_group_id for p in group_photos if p.burst_group_id != surviving_group_id
        }

        for photo in group_photos:
            photo.burst_group_id = surviving_group_id

        best_shot_id = select_best_shot(
            [
                PhotoForScoring(
                    id=p.id,
                    sharpness_score=_non_null(p.sharpness_score),
                    exposure_score=_non_null(p.exposure_score),
                )
                for p in group_photos
            ]
        )
        surviving_group = db.get(BurstGroup, surviving_group_id)
        assert surviving_group is not None
        surviving_group.best_shot_photo_id = best_shot_id

        if other_group_ids:
            db.flush()  # photos reassigned above must land before FK checks the delete
            for empty_group_id in other_group_ids:
                empty_group = db.get(BurstGroup, empty_group_id)
                if empty_group is not None:
                    db.delete(empty_group)

    db.flush()
    return len(computed_groups)
