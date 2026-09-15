import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exif_utils import extract_exif
from app.images import generate_thumbnails
from app.models import BurstGroup, Photo
from app.scoring import compute_content_hash
from app.storage import upload_bytes


def import_one_photo(
    db: Session,
    image_bytes: bytes,
    *,
    import_source: str,
    fallback_taken_at: datetime,
    google_photos_id: str | None = None,
) -> Photo:
    """Import a single photo: EXIF + thumbnails + R2 upload + DB rows.

    Creates a new singleton burst group for the photo (see plan: Data
    Model — every photo belongs to a group). Grouping photos into shared
    bursts and computing phash/sharpness/exposure scores is Phase 3 work;
    this function leaves those fields null.

    Shared between the one-off local import script (Phase 1) and the
    eventual Google Photos import pipeline (Phase 2) — the part of the
    pipeline downstream of "I have image bytes and a fallback date" does
    not change based on where the bytes came from.

    Rejects an exact re-upload of an already-imported file before doing
    any of the work below (see plan: prevent duplicate photos) —
    content_hash is computed first specifically so a duplicate costs one
    SELECT, not a wasted EXIF parse, thumbnail generation, and three R2
    uploads. Checked with the same check-then-insert-with-IntegrityError-
    fallback shape as get_or_create_species (app/jobs/classify_species.py):
    a SELECT handles the common sequential case (someone re-uploading a
    file that's already fully imported), the nested-transaction fallback
    handles the rare concurrent-upload race (two near-simultaneous
    uploads of the same file), and both paths raise the same friendly
    ValueError — the existing convention (see set_group_location) for
    "expected, user-facing failure, not a bug" — rather than a raw
    constraint violation reaching the browser.
    """
    content_hash = compute_content_hash(image_bytes)
    existing = db.execute(
        select(Photo).where(Photo.content_hash == content_hash)
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("This photo is already in your library")

    exif = extract_exif(image_bytes, fallback_taken_at)
    thumbnails = generate_thumbnails(image_bytes)

    photo_id = uuid.uuid4()
    r2_key_original = f"originals/{photo_id}.jpg"
    r2_key_thumb = f"web/{photo_id}-thumb.webp"
    r2_key_medium = f"web/{photo_id}-medium.webp"

    upload_bytes(r2_key_original, image_bytes, "image/jpeg")
    upload_bytes(r2_key_thumb, thumbnails.thumb, "image/webp")
    upload_bytes(r2_key_medium, thumbnails.medium, "image/webp")

    group = BurstGroup()
    db.add(group)
    db.flush()

    photo = Photo(
        id=photo_id,
        burst_group_id=group.id,
        google_photos_id=google_photos_id,
        import_source=import_source,
        content_hash=content_hash,
        r2_key_original=r2_key_original,
        r2_key_thumb=r2_key_thumb,
        r2_key_medium=r2_key_medium,
        width=exif.width,
        height=exif.height,
        taken_at=exif.taken_at,
        camera_make=exif.camera_make,
        camera_model=exif.camera_model,
        focal_length_mm=exif.focal_length_mm,
        aperture=exif.aperture,
        iso=exif.iso,
        shutter_speed=exif.shutter_speed,
        gps_lat=exif.gps_lat,
        gps_lng=exif.gps_lng,
        import_status="processed",
    )
    try:
        with db.begin_nested():
            db.add(photo)
            db.flush()
    except IntegrityError as e:
        raise ValueError("This photo is already in your library") from e

    group.best_shot_photo_id = photo.id
    db.flush()

    return photo
