from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_internal_token
from app.db import get_db
from app.jobs.import_upload import UploadImportResult, import_from_staged_upload

app = FastAPI(title="Bird Photos Worker")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sync/google-photos", dependencies=[Depends(require_internal_token)])
def sync_google_photos() -> dict[str, str]:
    # TODO(phase 2): enqueue the sync_requested job once the Google Photos
    # access spike (see plan) confirms the import approach.
    raise NotImplementedError("Google Photos sync not yet implemented")


class ImportFromUploadRequest(BaseModel):
    r2_keys: list[str]


@app.post(
    "/import/from-upload",
    dependencies=[Depends(require_internal_token)],
    response_model=list[UploadImportResult],
)
def import_from_upload(
    request: ImportFromUploadRequest,
    db: Session = Depends(get_db),  # noqa: B008 - idiomatic FastAPI dependency injection
) -> list[UploadImportResult]:
    """Called by the web app once the browser has PUT one or more files
    directly to R2 staging keys (see plan: manual upload). Small JSON
    payload only — the actual image bytes never pass through this
    request, sidestepping Vercel's 4.5MB serverless body limit."""
    return [import_from_staged_upload(db, key) for key in request.r2_keys]
