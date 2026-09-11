"""One-off Phase 1 import: load a folder of local JPEGs into R2 + the DB.

Usage:
    .venv/bin/python -m scripts.import_local_photos "/path/to/folder"

Skips Google Photos entirely (see plan: Implementation Phasing, Phase 1) —
photos are hand-picked and already on disk.
"""

import sys
from datetime import datetime
from pathlib import Path

from app.db import SessionLocal
from app.jobs.import_photo import import_one_photo

JPEG_EXTENSIONS = {".jpg", ".jpeg"}


def main(folder: str) -> None:
    paths = sorted(
        p for p in Path(folder).iterdir() if p.suffix.lower() in JPEG_EXTENSIONS
    )
    if not paths:
        print(f"No JPEGs found in {folder}")
        return

    db = SessionLocal()
    try:
        for path in paths:
            image_bytes = path.read_bytes()
            fallback_taken_at = datetime.fromtimestamp(path.stat().st_mtime)
            photo = import_one_photo(
                db,
                image_bytes,
                import_source="manual",
                fallback_taken_at=fallback_taken_at,
            )
            print(f"Imported {path.name} -> photo {photo.id} (taken_at={photo.taken_at})")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.import_local_photos <folder>")
        sys.exit(1)
    main(sys.argv[1])
