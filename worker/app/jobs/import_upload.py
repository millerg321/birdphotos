from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.jobs.import_photo import import_one_photo
from app.storage import delete_object, download_bytes


@dataclass
class UploadImportResult:
    r2_key: str
    photo_id: str | None
    error: str | None


def import_from_staged_upload(db: Session, r2_key: str) -> UploadImportResult:
    """Downloads a browser-uploaded file from its staging R2 key (see
    plan: manual upload — browser PUTs directly to R2 to sidestep
    Vercel's 4.5MB serverless body limit, which most real bird photos
    exceed), runs it through the same import_one_photo used by the
    local backfill script and the eventual Google Photos pipeline, then
    deletes the staging object. One photo's failure (e.g. a corrupt
    file) doesn't roll back the whole request — the caller commits/
    rolls back per photo and continues with the rest of the batch.
    """
    try:
        image_bytes = download_bytes(r2_key)
        photo = import_one_photo(
            db,
            image_bytes,
            import_source="manual_upload",
            fallback_taken_at=datetime.now(),
        )
        db.commit()
        delete_object(r2_key)
        return UploadImportResult(r2_key=r2_key, photo_id=str(photo.id), error=None)
    except Exception as e:  # reported to the caller, not swallowed
        db.rollback()
        return UploadImportResult(r2_key=r2_key, photo_id=None, error=str(e))
