import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select
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

logger = logging.getLogger(__name__)


def _non_null[T](value: T | None) -> T:
    """Narrows a nullable ORM column value for callers that already
    filtered the query on IS NOT NULL — SQLAlchemy's `.is_not(None)`
    doesn't narrow the mapped attribute's type, so mypy can't see it."""
    assert value is not None
    return value


def backfill_scores(db: Session) -> int:
    """Computes phash/sharpness/exposure for any photo missing them.
    Downloads the original from R2 since scoring needs real pixel data,
    not just the thumbnail (see plan: Burst Detection).

    One photo's failure (corrupt/undecodable image, an R2 hiccup)
    doesn't abort the rest of the batch — same reasoning as
    classify_new_groups_sync's per-group isolation, added after a
    similar unprotected loop there took down an entire large-batch
    classify run in production. No savepoint needed here (unlike that
    one): this only mutates already-tracked ORM attributes, nothing is
    written to the DB until the single db.flush() at the end, so
    there's no pending write to protect — just skip the photo, leaving
    it to retry on the next run since it's still missing a phash.
    """
    photos = db.execute(
        select(Photo).where(Photo.phash.is_(None))
    ).scalars().all()

    scored = 0
    for photo in photos:
        try:
            original = download_bytes(photo.r2_key_original)
            photo.phash = compute_phash(original)
            photo.sharpness_score = compute_sharpness(original)
            photo.exposure_score = compute_exposure(original)
        except Exception:
            logger.exception("Failed to score photo %s", photo.id)
            continue
        scored += 1

    db.flush()
    return scored


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


def _delete_empty_group(db: Session, group: BurstGroup) -> None:
    """Deletes a burst_groups row that has no photos left. Clears its own
    best-shot FK columns and removes any species/tags still attached to
    it first — both carry a NOT NULL FK to burst_groups that would
    otherwise turn the delete below into a ForeignKeyViolation. Callers
    that want to preserve species/tags (e.g. merge_groups) must reassign
    them to a surviving group before calling this; anything left here is
    genuinely discarded.
    """
    db.execute(delete(BurstGroupSpecies).where(BurstGroupSpecies.burst_group_id == group.id))
    db.execute(delete(BurstGroupTag).where(BurstGroupTag.burst_group_id == group.id))
    group.best_shot_photo_id = None
    group.best_shot_override_photo_id = None
    db.flush()
    db.delete(group)


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
        _delete_empty_group(db, from_group)

    db.flush()
    return into_group_id


def _replace_best_shot_after_removal(
    group: BurstGroup, removed_photo_id: uuid.UUID, remaining: Sequence[Photo]
) -> None:
    """Shared by remove_photo_from_group and delete_photo: picks a new
    best shot for a group after one of its photos left, from whatever
    scores are available among what remains. If nothing is scored yet,
    still clears a best-shot/override reference that pointed at the
    removed photo — otherwise the group would display a "best shot"
    that's no longer even in it."""
    scored = [
        p for p in remaining if p.sharpness_score is not None and p.exposure_score is not None
    ]
    if scored:
        group.best_shot_photo_id = select_best_shot(
            [
                PhotoForScoring(
                    id=p.id,
                    sharpness_score=_non_null(p.sharpness_score),
                    exposure_score=_non_null(p.exposure_score),
                )
                for p in sorted(scored, key=lambda p: p.taken_at)
            ]
        )
    elif group.best_shot_photo_id == removed_photo_id:
        group.best_shot_photo_id = remaining[0].id

    if group.best_shot_override_photo_id == removed_photo_id:
        group.best_shot_override_photo_id = None


def remove_photo_from_group(db: Session, photo_id: uuid.UUID) -> uuid.UUID:
    """Splits one photo out of its current burst group into a new,
    unlocked singleton group (see plan: manual upload / grouping
    overrides — the fix for an accidental merge, since merging two whole
    groups is all-or-nothing). Unlocked so the photo re-enters normal
    automatic regrouping; the photos left behind stay locked, since
    removing one photo doesn't change the merge decision covering the
    rest. If only one photo remains in the old group afterward, it's
    unlocked too — a "merge" of one photo isn't a merge, and there's
    nothing left for regroup_all to protect.
    """
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise ValueError("Photo not found")

    old_group_id = photo.burst_group_id
    old_group = db.get(BurstGroup, old_group_id)
    assert old_group is not None

    photos_before_removal = db.execute(
        select(Photo).where(Photo.burst_group_id == old_group_id)
    ).scalars().all()
    if len(photos_before_removal) <= 1:
        raise ValueError("Photo is already in its own group")

    new_group = BurstGroup()
    db.add(new_group)
    db.flush()

    photo.burst_group_id = new_group.id
    photo.grouping_locked = False
    db.flush()
    new_group.best_shot_photo_id = photo.id

    remaining = db.execute(
        select(Photo).where(Photo.burst_group_id == old_group_id)
    ).scalars().all()
    if len(remaining) == 1:
        remaining[0].grouping_locked = False
    _replace_best_shot_after_removal(old_group, photo_id, remaining)

    db.flush()
    return new_group.id


@dataclass
class DeletePhotoOutcome:
    r2_keys: list[str]
    # None if this was the group's last photo and it was deleted too —
    # tells the caller (the web app) whether to redirect away from the
    # now-gone group page or just refresh it in place.
    surviving_group_id: uuid.UUID | None


def delete_photo(db: Session, photo_id: uuid.UUID) -> DeletePhotoOutcome:
    """Permanently deletes one photo's DB row. Returns its R2 keys
    (original/thumb/medium) for the caller to delete from R2 — only
    after committing this deletion, not before (see
    import_from_staged_upload for the same before/after-commit
    ordering rationale: never leave R2 objects deleted while a DB
    transaction referencing them could still roll back).

    If this was the group's only photo, the now-empty group is deleted
    too; otherwise a new best shot is picked from what's left.
    """
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise ValueError("Photo not found")

    group_id = photo.burst_group_id
    keys = [photo.r2_key_original, photo.r2_key_thumb, photo.r2_key_medium]
    group = db.get(BurstGroup, group_id)
    assert group is not None

    # Computed before the delete below — identical to what a post-delete
    # query would return, since it already excludes photo_id.
    remaining = db.execute(
        select(Photo).where(Photo.burst_group_id == group_id, Photo.id != photo_id)
    ).scalars().all()

    # The group's best-shot/override FKs must stop pointing at photo_id
    # before it's deleted, or the delete below fails with a
    # ForeignKeyViolation — same ordering constraint as delete_group.
    if remaining:
        _replace_best_shot_after_removal(group, photo_id, remaining)
    else:
        group.best_shot_photo_id = None
        group.best_shot_override_photo_id = None
    db.flush()

    db.delete(photo)
    db.flush()

    if not remaining:
        _delete_empty_group(db, group)
        db.flush()
        return DeletePhotoOutcome(r2_keys=keys, surviving_group_id=None)

    return DeletePhotoOutcome(r2_keys=keys, surviving_group_id=group_id)


def delete_group(db: Session, group_id: uuid.UUID) -> list[str]:
    """Permanently deletes an entire burst group and all its photos'
    DB rows. Returns every deleted photo's R2 keys for the caller to
    delete from R2 after committing (same ordering rationale as
    delete_photo)."""
    group = db.get(BurstGroup, group_id)
    if group is None:
        raise ValueError("Group not found")

    # Clear the group's own best-shot/override FKs before deleting its
    # photos below — they point at one of those photos, so deleting it
    # first would fail with a ForeignKeyViolation (same ordering
    # constraint as delete_photo).
    group.best_shot_photo_id = None
    group.best_shot_override_photo_id = None
    db.flush()

    photos = db.execute(select(Photo).where(Photo.burst_group_id == group_id)).scalars().all()
    keys: list[str] = []
    for photo in photos:
        keys.extend([photo.r2_key_original, photo.r2_key_thumb, photo.r2_key_medium])
        db.delete(photo)
    db.flush()

    _delete_empty_group(db, group)
    db.flush()
    return keys
