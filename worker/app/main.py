from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import require_internal_token
from app.classification import SpeciesClassification, classify_photo_sync, get_anthropic_client
from app.db import get_db
from app.jobs.classify_species import (
    classify_new_groups_sync,
    clear_unreviewed_ai_suggestions,
    reclassify_group_with_better_model,
)
from app.jobs.group_bursts import (
    backfill_scores,
    delete_group,
    delete_photo,
    merge_groups,
    regroup_all,
    remove_photo_from_group,
)
from app.jobs.import_upload import UploadImportResult, import_from_staged_upload
from app.locations import set_group_location
from app.storage import delete_object

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
    classified: int


# Arbitrary bigint identifying this job for a Postgres advisory lock —
# any value works, it just has to stay constant across calls and not
# collide with another lock use in this app (there isn't one yet).
_BACKFILL_AND_GROUP_LOCK_KEY = 727100


@app.post(
    "/jobs/backfill-and-group",
    dependencies=[Depends(require_internal_token)],
    response_model=BackfillAndGroupResult,
)
def run_backfill_and_group(
    db: Session = Depends(get_db),  # noqa: B008 - idiomatic FastAPI dependency injection
) -> BackfillAndGroupResult:
    """Manual trigger for the same scoring/grouping pass scripts/backfill_and_group.py
    runs, plus incremental AI species classification for whatever comes
    out newly grouped — deliberately not part of the upload flow itself
    (see plan: manual upload). regroup_all rescans every scored photo
    rather than just what's new, so running it per-upload would make
    each upload's response wait on an ever-growing full-library pass;
    call this endpoint after a batch of uploads instead. May go away
    if/once uploads get proper incremental grouping.

    Classification runs last, after grouping has settled — classifying
    per photo before regrouping would waste API calls per individual
    photo instead of once per final burst group (see plan: AI Species
    Classification, cost control by construction). Uses
    classify_photo_sync rather than the Batch API's submit-then-poll
    (scripts/classify_backlog.py) since manual uploads are a small,
    on-demand trickle, not a large one-off backlog.

    Guarded by a Postgres session-level advisory lock (not the
    transactional pg_advisory_xact_lock — this function's own three
    db.commit() calls would release that before classify_new_groups_
    sync even runs): a second concurrent call to this endpoint now
    fails fast with 409 instead of racing the first. Real production
    incident, not a hypothetical — classify_new_groups_sync decides
    which groups still need classification from burst_group_species,
    but nothing commits until this function's own commits, so two
    overlapping requests (the "Score, group & classify" button is now
    on both /upload and /review, and each request can take a while —
    a real Anthropic API call per group) both saw the same groups as
    unclassified and each inserted a full set of candidates, silently
    doubling them (confirmed: paired rows, identical species_id, same
    model, near- but not bitwise-identical confidence — two separate
    API calls, 44 seconds apart). Duplicates from before this fix were
    cleaned up by scripts/fix_duplicate_pending_candidates.py.
    """
    got_lock = db.execute(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": _BACKFILL_AND_GROUP_LOCK_KEY}
    ).scalar()
    if not got_lock:
        raise HTTPException(
            status_code=409, detail="A rescan is already running — try again shortly."
        )
    try:
        scored = backfill_scores(db)
        db.commit()
        groups = regroup_all(db)
        db.commit()
        classified = classify_new_groups_sync(db)
        db.commit()
        return BackfillAndGroupResult(scored=scored, groups=groups, classified=classified)
    finally:
        # unlock_all, not unlocking just this key: a session-level
        # lock outlives db.commit(), so it must be released explicitly
        # before this connection goes back to SQLAlchemy's pool for
        # reuse by an unrelated later request — unlock_all is a
        # deliberate safety margin against ever leaking a held lock
        # onto a pooled connection.
        db.execute(text("SELECT pg_advisory_unlock_all()"))


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


class RemovePhotoFromGroupRequest(BaseModel):
    photo_id: UUID


class RemovePhotoFromGroupResult(BaseModel):
    group_id: UUID


@app.post(
    "/jobs/remove-photo-from-group",
    dependencies=[Depends(require_internal_token)],
    response_model=RemovePhotoFromGroupResult,
)
def run_remove_photo_from_group(
    request: RemovePhotoFromGroupRequest,
    db: Session = Depends(get_db),  # noqa: B008 - idiomatic FastAPI dependency injection
) -> RemovePhotoFromGroupResult:
    """Splits one photo back out of a merged group into its own new group
    (see plan: manual upload / grouping overrides) — the undo for an
    accidental merge_groups call, since merging is all-or-nothing at the
    group level but unmerging works per photo."""
    group_id = remove_photo_from_group(db, request.photo_id)
    db.commit()
    return RemovePhotoFromGroupResult(group_id=group_id)


class DeletePhotoRequest(BaseModel):
    photo_id: UUID


class DeletePhotoResult(BaseModel):
    # None if this was the group's last photo — the group's gone too, so
    # the web app knows to redirect away from its now-404 detail page.
    surviving_group_id: UUID | None


@app.post(
    "/jobs/delete-photo",
    dependencies=[Depends(require_internal_token)],
    response_model=DeletePhotoResult,
)
def run_delete_photo(
    request: DeletePhotoRequest,
    db: Session = Depends(get_db),  # noqa: B008 - idiomatic FastAPI dependency injection
) -> DeletePhotoResult:
    """Permanently deletes one photo (see plan: manual upload / grouping
    overrides)."""
    outcome = delete_photo(db, request.photo_id)
    db.commit()
    for key in outcome.r2_keys:
        delete_object(key)
    return DeletePhotoResult(surviving_group_id=outcome.surviving_group_id)


class DeleteGroupRequest(BaseModel):
    group_id: UUID


class DeleteGroupResult(BaseModel):
    deleted: bool


@app.post(
    "/jobs/delete-group",
    dependencies=[Depends(require_internal_token)],
    response_model=DeleteGroupResult,
)
def run_delete_group(
    request: DeleteGroupRequest,
    db: Session = Depends(get_db),  # noqa: B008 - idiomatic FastAPI dependency injection
) -> DeleteGroupResult:
    """Permanently deletes an entire burst group and all its photos (see
    plan: manual upload / grouping overrides)."""
    keys = delete_group(db, request.group_id)
    db.commit()
    for key in keys:
        delete_object(key)
    return DeleteGroupResult(deleted=True)


class SetGroupLocationRequest(BaseModel):
    group_id: UUID
    place_name: str


class SetGroupLocationResult(BaseModel):
    location_id: UUID
    name: str
    lat: float
    lng: float


@app.post(
    "/jobs/set-group-location",
    dependencies=[Depends(require_internal_token)],
    response_model=SetGroupLocationResult,
)
def run_set_group_location(
    request: SetGroupLocationRequest,
    db: Session = Depends(get_db),  # noqa: B008 - idiomatic FastAPI dependency injection
) -> SetGroupLocationResult:
    """Manually assigns a location to every photo in a group, geocoded
    from a free-text place name via Nominatim (see plan: Manual Location
    Fallback) — meant to be set before running classification, since
    location materially changes AI species suggestions (see plan: AI
    Species Classification). Also clears this group's own unreviewed AI
    suggestions (never a confirmed one) so a later classify run treats
    it as unclassified again, rather than leaving stale pre-location
    suggestions sitting alongside nothing new."""
    try:
        location = set_group_location(db, request.group_id, request.place_name)
    except ValueError as e:
        # An unrecognized place name is a normal, expected user-input
        # outcome (unlike the other endpoints' ValueErrors, which mostly
        # guard against races/bugs) — surface the real reason via
        # HTTPException's detail rather than a generic 500, so the web
        # app's inline error actually tells the user something useful.
        raise HTTPException(status_code=422, detail=str(e)) from e
    clear_unreviewed_ai_suggestions(db, [request.group_id])
    db.commit()
    return SetGroupLocationResult(
        location_id=location.id,
        name=location.name,
        lat=location.center_lat,
        lng=location.center_lng,
    )


class ReclassifyGroupRequest(BaseModel):
    group_id: UUID


class ReclassifyGroupResult(BaseModel):
    reclassified: bool


@app.post(
    "/jobs/reclassify-group",
    dependencies=[Depends(require_internal_token)],
    response_model=ReclassifyGroupResult,
)
def run_reclassify_group(
    request: ReclassifyGroupRequest,
    db: Session = Depends(get_db),  # noqa: B008 - idiomatic FastAPI dependency injection
) -> ReclassifyGroupResult:
    """Manual escalation to a stronger model (see plan: AI Species
    Classification — "optional Sonnet-5 escalation for low-confidence
    results") for a specific group whose default-model classification
    came back poor — triggered from the review queue, not automatic."""
    try:
        reclassify_group_with_better_model(db, request.group_id)
    except ValueError as e:
        # Same reasoning as set-group-location: a real, expected failure
        # mode a human can hit from the UI (e.g. the group somehow has
        # no best shot yet), not a bug — surface the message.
        raise HTTPException(status_code=422, detail=str(e)) from e
    db.commit()
    return ReclassifyGroupResult(reclassified=True)


@app.post(
    "/identify",
    dependencies=[Depends(require_internal_token)],
    response_model=SpeciesClassification,
)
async def identify_photo(file: UploadFile = File(...)) -> SpeciesClassification:  # noqa: B008
    """Backs the public, anonymous /identify page (see plan: ephemeral
    photo identification) — deliberately the only endpoint in this app
    with no `db` dependency at all. Nothing about the request is ever
    persisted: no Photo, BurstGroup, or Species row, no R2 upload. The
    caller (web/app/api/identify/route.ts) is itself unauthenticated,
    but still the only thing allowed to reach this endpoint — gated by
    the same X-Internal-Token as every other job here — and is where
    rate limiting and a daily cost cap live, since this endpoint makes
    a real (small) Anthropic API call per request. The web route
    always sends a canvas-re-encoded JPEG, so media_type is fixed
    rather than trusting a client-supplied content type."""
    image_bytes = await file.read()
    client = get_anthropic_client()
    return classify_photo_sync(client, image_bytes, media_type="image/jpeg")
