"""Backfills Photo.content_hash for rows imported before duplicate
detection existed (see plan: prevent duplicate photos,
app/jobs/import_photo.py), and reports any exact duplicates already
sitting in the library while doing it.

For each photo missing a hash: downloads its original from R2 (same
per-photo download this script's sibling backfill_scores does for
phash/sharpness/exposure), computes the hash, and commits it — one
commit per photo, not batched into a single transaction. That's
deliberate, not just for resumability if the script dies partway
through a big library: a nested-transaction (SAVEPOINT) rollback
inside one shared transaction turned out not to cleanly recover the
session for the next query when other photos' hashes from earlier in
the same run were still pending alongside it (found running this for
real against production — the recovery path itself raised
PendingRollbackError). Committing per photo sidesteps that entirely:
each row's UPDATE is its own transaction, so a duplicate's failed
commit can't entangle with anything else pending.

If a commit fails on the content_hash unique constraint, another
photo — either one already hashed by a previous run, or one just
committed earlier in this same run — already has that exact hash.
That failure *is* the duplicate report: this script doesn't run a
separate comparison pass, it reuses the same constraint the live
import path relies on. The loser keeps content_hash NULL (harmless —
NULLs don't collide with each other) and gets listed in the summary;
nothing is deleted automatically. Review the report and remove
redundant groups yourself via the existing /groups/[id] delete UI if
you want to.

Usage:
    .venv/bin/python -m scripts.backfill_content_hashes
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Photo
from app.scoring import compute_content_hash
from app.storage import download_bytes


def main() -> None:
    db = SessionLocal()
    try:
        photo_ids = (
            db.execute(select(Photo.id).where(Photo.content_hash.is_(None))).scalars().all()
        )

        hashed = 0
        duplicates: list[tuple[Photo, uuid.UUID]] = []
        for photo_id in photo_ids:
            photo = db.get(Photo, photo_id)
            assert photo is not None

            try:
                original = download_bytes(photo.r2_key_original)
                content_hash = compute_content_hash(original)
            except Exception as e:
                print(f"Photo {photo.id}: skipped, could not read original ({e})")
                continue

            photo.content_hash = content_hash
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                existing = db.execute(
                    select(Photo).where(Photo.content_hash == content_hash)
                ).scalar_one()
                duplicates.append((existing, photo_id))
                print(
                    f"Duplicate: photo {photo_id} (group {photo.burst_group_id}) "
                    f"matches already-hashed photo {existing.id} "
                    f"(group {existing.burst_group_id})"
                )
                continue

            hashed += 1

        print(f"Hashed {hashed} photo(s), found {len(duplicates)} duplicate(s)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
