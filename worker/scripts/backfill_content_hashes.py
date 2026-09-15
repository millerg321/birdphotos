"""Backfills Photo.content_hash for rows imported before duplicate
detection existed (see plan: prevent duplicate photos,
app/jobs/import_photo.py), and reports any exact duplicates already
sitting in the library while doing it.

For each photo missing a hash: downloads its original from R2 (same
per-photo download this script's sibling backfill_scores does for
phash/sharpness/exposure), computes the hash, and tries to save it.
If that save fails on the content_hash unique constraint, another
photo — either a real duplicate found and backfilled earlier in this
same run, or one hashed by a previous run — already has that exact
hash. That failure *is* the duplicate report: this script doesn't run
a separate comparison pass, it reuses the same constraint the live
import path relies on. The loser keeps content_hash NULL (harmless —
NULLs don't collide with each other) and gets listed in the summary;
nothing is deleted automatically. Review the report and remove
redundant groups yourself via the existing /groups/[id] delete UI if
you want to.

Usage:
    .venv/bin/python -m scripts.backfill_content_hashes
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Photo
from app.scoring import compute_content_hash
from app.storage import download_bytes


def main() -> None:
    db = SessionLocal()
    try:
        photos = (
            db.execute(select(Photo).where(Photo.content_hash.is_(None))).scalars().all()
        )

        hashed = 0
        duplicates: list[tuple[Photo, Photo]] = []
        for photo in photos:
            try:
                original = download_bytes(photo.r2_key_original)
                content_hash = compute_content_hash(original)
            except Exception as e:
                print(f"Photo {photo.id}: skipped, could not read original ({e})")
                continue

            photo.content_hash = content_hash
            try:
                with db.begin_nested():
                    db.flush()
            except IntegrityError:
                photo.content_hash = None
                existing = db.execute(
                    select(Photo).where(Photo.content_hash == content_hash)
                ).scalar_one()
                duplicates.append((existing, photo))
                print(
                    f"Duplicate: photo {photo.id} (group {photo.burst_group_id}) "
                    f"matches already-hashed photo {existing.id} "
                    f"(group {existing.burst_group_id})"
                )
                continue

            hashed += 1

        db.commit()
        print(f"Hashed {hashed} photo(s), found {len(duplicates)} duplicate(s)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
