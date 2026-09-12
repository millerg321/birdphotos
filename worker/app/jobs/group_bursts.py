import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.grouping import (
    PhotoForGrouping,
    PhotoForScoring,
    group_by_burst,
    select_best_shot,
)
from app.models import BurstGroup, BurstGroupSpecies, BurstGroupTag, Photo
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
            Photo.grouping_locked.is_(False),
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


def merge_groups(db: Session, into_group_id: uuid.UUID, from_group_id: uuid.UUID) -> uuid.UUID:
    """Manually merges from_group_id's photos into into_group_id (see
    plan: manual upload / grouping overrides — the UI action for bursts
    the automatic threshold-based grouping splits apart, e.g. a late
    outlier frame too far in time/hash from the rest of its burst).

    Locks every resulting photo's grouping_locked flag so regroup_all
    (which otherwise recomputes every group from scratch on each run)
    never silently re-splits this merge apart later — mirrors
    best_shot_override_photo_id's permanent-override semantics. A
    locked group is excluded from all future automatic regrouping,
    including absorbing new photos, until explicitly unlocked (not yet
    exposed in the UI — no reset action exists for this yet, unlike
    best-shot overrides).
    """
    if into_group_id == from_group_id:
        raise ValueError("Cannot merge a group with itself")

    from_photos = db.execute(
        select(Photo).where(Photo.burst_group_id == from_group_id)
    ).scalars().all()
    if not from_photos:
        # Idempotent no-op rather than an error: a duplicate submission of
        # the same merge (e.g. a double-click before the UI could disable
        # the button) racing an already-successful call lands here with
        # nothing left to do, not a real failure.
        return into_group_id

    for photo in from_photos:
        photo.burst_group_id = into_group_id
        photo.grouping_locked = True
    db.flush()

    into_photos = db.execute(
        select(Photo).where(Photo.burst_group_id == into_group_id)
    ).scalars().all()
    for photo in into_photos:
        photo.grouping_locked = True

    # Best shot needs every merged photo's scores — if some aren't scored
    # yet (e.g. merging right after upload, before backfill_scores has
    # run), leave the existing best_shot_photo_id as-is rather than
    # picking from a partial/unscored set; a later backfill + merge (or
    # regroup, though locked photos are now excluded from that) can
    # correct it once scores exist.
    scored = [
        p for p in into_photos
        if p.sharpness_score is not None and p.exposure_score is not None
    ]
    if scored:
        best_shot_id = select_best_shot(
            [
                PhotoForScoring(
                    id=p.id,
                    sharpness_score=_non_null(p.sharpness_score),
                    exposure_score=_non_null(p.exposure_score),
                )
                for p in sorted(scored, key=lambda p: p.taken_at)
            ]
        )
        into_group = db.get(BurstGroup, into_group_id)
        assert into_group is not None
        into_group.best_shot_photo_id = best_shot_id

    # Species candidates and tags also carry a NOT NULL FK to burst_groups
    # (tags via a composite PK including it) — reassign both onto
    # into_group_id or the delete below fails with a ForeignKeyViolation,
    # the same way photos would without the reassignment above.
    for candidate in db.execute(
        select(BurstGroupSpecies).where(BurstGroupSpecies.burst_group_id == from_group_id)
    ).scalars():
        candidate.burst_group_id = into_group_id

    existing_tag_ids = {
        tag.tag_id
        for tag in db.execute(
            select(BurstGroupTag).where(BurstGroupTag.burst_group_id == into_group_id)
        ).scalars()
    }
    for tag in db.execute(
        select(BurstGroupTag).where(BurstGroupTag.burst_group_id == from_group_id)
    ).scalars():
        if tag.tag_id in existing_tag_ids:
            db.delete(tag)  # already tagged on into_group_id — avoid a composite-PK clash
        else:
            tag.burst_group_id = into_group_id
    db.flush()

    from_group = db.get(BurstGroup, from_group_id)
    if from_group is not None:
        # Clear this group's own best-shot FK columns before delete — they
        # point at photos that just moved to into_group_id.
        from_group.best_shot_photo_id = None
        from_group.best_shot_override_photo_id = None
        db.flush()
        db.delete(from_group)

    db.flush()
    return into_group_id
