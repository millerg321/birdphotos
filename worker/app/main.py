from uuid import UUID

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_internal_token
from app.db import get_db
from app.jobs.group_bursts import backfill_scores, merge_groups, regroup_all
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


class BackfillAndGroupResult(BaseModel):
    scored: int
    groups: int


@app.post(
    "/jobs/backfill-and-group",
    dependencies=[Depends(require_internal_token)],
    response_model=BackfillAndGroupResult,
)
def run_backfill_and_group(
    db: Session = Depends(get_db),  # noqa: B008 - idiomatic FastAPI dependency injection
) -> BackfillAndGroupResult:
    """Manual trigger for the same scoring/grouping pass scripts/backfill_and_group.py
    runs — deliberately not part of the upload flow itself (see plan:
    manual upload). regroup_all rescans every scored photo rather than
    just what's new, so running it per-upload would make each upload's
    response wait on an ever-growing full-library pass; call this
    endpoint after a batch of uploads instead. May go away if/once
    uploads get proper incremental grouping."""
    scored = backfill_scores(db)
    db.commit()
    groups = regroup_all(db)
    db.commit()
    return BackfillAndGroupResult(scored=scored, groups=groups)


class MergeGroupsRequest(BaseModel):
    into_group_id: UUID
    from_group_id: UUID


class MergeGroupsResult(BaseModel):
    group_id: UUID


@app.post(
    "/jobs/merge-groups",
    dependencies=[Depends(require_internal_token)],
    response_model=MergeGroupsResult,
)
def run_merge_groups(
    request: MergeGroupsRequest,
    db: Session = Depends(get_db),  # noqa: B008 - idiomatic FastAPI dependency injection
) -> MergeGroupsResult:
    """Manual merge trigger for the group-detail page's "merge with
    previous/next group" action (see plan: manual upload / grouping
    overrides) — for bursts the automatic threshold-based grouping
    splits apart despite being the same real burst."""
    group_id = merge_groups(db, request.into_group_id, request.from_group_id)
    db.commit()
    return MergeGroupsResult(group_id=group_id)
