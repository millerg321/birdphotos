import re
import uuid

from anthropic.types import TextBlockParam
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.classification import (
    CLASSIFICATION_MODEL,
    ESCALATION_CLASSIFICATION_MODEL,
    SpeciesClassification,
    build_classification_prompt,
    classify_photo_sync,
    get_anthropic_client,
    image_block,
)
from app.models import BurstGroup, BurstGroupSpecies, Location, Photo, Species
from app.storage import download_bytes

# Hand-written rather than derived from SpeciesClassification.model_json_schema():
# client.messages.parse() (used by the synchronous incremental path in
# app/classification.py) does its own Pydantic->schema conversion
# internally, and that conversion isn't part of the documented public
# API — the Batch API has no .parse() equivalent, so batch requests go
# through the raw output_config.format path instead (see plan skill
# docs: "Raw Schema"). Writing this by hand for our one simple schema
# avoids guessing at SDK-internal schema generation; the result is
# still validated through SpeciesClassification after parsing.
#
# No `maxItems` on the candidates array: verified empirically (all 11
# real batch requests errored with "For 'array' type, property
# 'maxItems' is not supported") — Claude's structured-output schema
# validator doesn't support it. The "up to 3" cap is enforced by the
# prompt plus SpeciesClassification's own max_length=3 after parsing.
_CLASSIFICATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "common_name": {"type": "string"},
                    "scientific_name": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                },
                "required": ["common_name", "scientific_name", "confidence"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": ["string", "null"]},
    },
    "required": ["candidates", "notes"],
    "additionalProperties": False,
}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "unknown"


def get_or_create_species(db: Session, common_name: str, scientific_name: str | None) -> Species:
    """Matches on lowercase common_name — the plan's "lighter v1" for
    Phase 4, ahead of seeding a proper eBird taxonomy table. Accepts
    some risk of near-duplicate species rows from inconsistent AI
    phrasing; a human reviewing the /review queue can merge later."""
    existing = db.execute(
        select(Species).where(Species.common_name.ilike(common_name))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    species = Species(
        common_name=common_name,
        scientific_name=scientific_name,
        slug=_slugify(common_name),
    )
    db.add(species)
    db.flush()
    return species


def _groups_needing_classification(db: Session) -> list[BurstGroup]:
    already_classified = select(BurstGroupSpecies.burst_group_id).distinct()
    return list(
        db.execute(
            select(BurstGroup).where(BurstGroup.id.not_in(already_classified))
        ).scalars()
    )


def clear_unreviewed_ai_suggestions(db: Session, group_ids: list[uuid.UUID]) -> None:
    """Deletes 'ai_suggested' candidates for the given groups, but never a
    'confirmed' row — used before a deliberate reclassification pass (e.g.
    after assigning locations) so stale suggestions don't linger alongside
    the new ones. A human's prior confirmation should survive a re-run."""
    db.execute(
        delete(BurstGroupSpecies).where(
            BurstGroupSpecies.burst_group_id.in_(group_ids),
            BurstGroupSpecies.source == "ai_suggested",
            BurstGroupSpecies.status != "confirmed",
        )
    )
    db.flush()


def submit_batch_classification(
    db: Session, group_ids: list[uuid.UUID] | None = None
) -> str | None:
    """One request per burst group (not per photo — see plan: cost
    control by construction), using each group's best-shot medium image
    and, when that photo has an assigned Location, the location's name
    as classification context — verified to materially change results
    (without it, classification tended toward whichever similar-looking
    species is most common in the model's training data, e.g. North
    American species suggested for UK/Borneo/South African photos).

    group_ids: classify exactly these groups, bypassing the "already
    classified" filter — used for a deliberate reclassification pass
    (e.g. after assigning locations to existing photos). Groups that
    already have a 'confirmed' candidate are skipped even here — a
    human's answer is ground truth, and resubmitting it would just
    resurrect an already-settled group in the /review queue alongside
    its confirmed row (hit this exactly while testing the reclassify
    path). Omit group_ids for the normal incremental/backlog behavior.
    Returns None if there's nothing to classify.
    """
    if group_ids is not None:
        already_confirmed = select(BurstGroupSpecies.burst_group_id).where(
            BurstGroupSpecies.status == "confirmed"
        )
        groups = list(
            db.execute(
                select(BurstGroup).where(
                    BurstGroup.id.in_(group_ids), BurstGroup.id.not_in(already_confirmed)
                )
            ).scalars()
        )
    else:
        groups = _groups_needing_classification(db)
    if not groups:
        return None

    requests = []
    for group in groups:
        best_shot_id = group.best_shot_override_photo_id or group.best_shot_photo_id
        photo = db.get(Photo, best_shot_id)
        assert photo is not None
        image_bytes = download_bytes(photo.r2_key_medium)
        location_hint = _location_hint_for_photo(db, photo)

        requests.append(
            Request(
                custom_id=str(group.id),
                params=MessageCreateParamsNonStreaming(
                    model=CLASSIFICATION_MODEL,
                    max_tokens=1024,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                image_block(image_bytes, "image/webp"),
                                TextBlockParam(
                                    type="text", text=build_classification_prompt(location_hint)
                                ),
                            ],
                        }
                    ],
                    output_config={
                        "format": {"type": "json_schema", "schema": _CLASSIFICATION_JSON_SCHEMA}
                    },
                ),
            )
        )

    client = get_anthropic_client()
    batch = client.messages.batches.create(requests=requests)
    return batch.id


def ingest_batch_results(db: Session, batch_id: str) -> int:
    """Call once the batch's processing_status is "ended". Inserts up to
    3 candidate burst_group_species rows per succeeded group (source
    'ai_suggested', status 'pending_review' — see app/queries.py
    get_effective_species for how these resolve later)."""
    client = get_anthropic_client()
    ingested = 0

    for result in client.messages.batches.results(batch_id):
        if result.result.type != "succeeded":
            continue

        group_id = uuid.UUID(result.custom_id)
        text = next(
            (b.text for b in result.result.message.content if b.type == "text"), None
        )
        if text is None:
            continue
        try:
            classification = SpeciesClassification.model_validate_json(text)
        except ValidationError:
            # No maxItems in the API-level schema (see comment above), so
            # an oversized or malformed response is possible in principle
            # — skip this one group rather than losing the whole batch.
            continue

        _insert_candidates(db, group_id, classification)
        ingested += 1

    db.flush()
    return ingested


def _insert_candidates(
    db: Session,
    group_id: uuid.UUID,
    classification: SpeciesClassification,
    model: str = CLASSIFICATION_MODEL,
) -> None:
    """Shared by ingest_batch_results, classify_new_groups_sync, and
    reclassify_group_with_better_model: one burst_group_species row per
    candidate (source 'ai_suggested', status 'pending_review' — see
    app/queries.py get_effective_species). model must be whichever model
    actually produced this classification, not assumed from the default
    — reclassify_group_with_better_model passes
    ESCALATION_CLASSIFICATION_MODEL here; caught by testing that the
    right model reached classify_photo_sync, but missed that this
    function silently re-hardcoded CLASSIFICATION_MODEL regardless,
    stamping every row's audit trail wrong."""
    for candidate in classification.candidates:
        species = get_or_create_species(db, candidate.common_name, candidate.scientific_name)
        db.add(
            BurstGroupSpecies(
                burst_group_id=group_id,
                species_id=species.id,
                raw_label=candidate.common_name,
                source="ai_suggested",
                confidence=candidate.confidence,
                status="pending_review",
                model_id=model,
                raw_response=classification.model_dump(),
            )
        )


def classify_new_groups_sync(db: Session) -> int:
    """Synchronous incremental classification for the manual upload flow
    (see plan: AI Species Classification / manual upload). Classifies
    every group that doesn't have a species candidate yet, one group at
    a time via classify_photo_sync — meant to run as part of the same
    "Score & group new photos" action used after uploading.

    The bulk backlog path (scripts/classify_backlog.py) uses the
    cheaper Batch API instead, but its submit-then-poll shape doesn't
    suit classifying a handful of new uploads on demand; this costs a
    real (if small — Haiku, per-group not per-photo) API call per
    group every time it runs, in exchange for an immediate result.

    A group whose photo can't be identified at all (empty candidates,
    per the prompt's own instruction) gets no burst_group_species row
    and so will be retried on the next run — same behavior as the
    batch path, not something introduced here.
    """
    groups = _groups_needing_classification(db)
    if not groups:
        return 0

    client = get_anthropic_client()
    classified = 0
    for group in groups:
        best_shot_id = group.best_shot_override_photo_id or group.best_shot_photo_id
        if best_shot_id is None:
            continue
        photo = db.get(Photo, best_shot_id)
        if photo is None:
            continue
        image_bytes = download_bytes(photo.r2_key_medium)
        location_hint = _location_hint_for_photo(db, photo)

        classification = classify_photo_sync(client, image_bytes, "image/webp", location_hint)
        _insert_candidates(db, group.id, classification)
        classified += 1

    db.flush()
    return classified


def _location_hint_for_photo(db: Session, photo: Photo) -> str | None:
    if photo.location_id is None:
        return None
    location = db.get(Location, photo.location_id)
    return location.name if location is not None else None


def reclassify_group_with_better_model(db: Session, group_id: uuid.UUID) -> None:
    """Manual escalation for one group whose Haiku classification came
    back poor (see plan: AI Species Classification — "optional Sonnet-5
    escalation for low-confidence results", brought forward from a
    stretch goal to an on-demand per-group action triggered from the
    review queue, rather than an automatic blanket switch — the point is
    a human judging one specific bad result, not paying Sonnet's cost
    for every photo).

    Clears this group's own unreviewed AI suggestions first (never a
    confirmed one) so the Sonnet candidates replace them cleanly rather
    than piling up in the review queue alongside the Haiku ones that
    prompted the re-check.
    """
    group = db.get(BurstGroup, group_id)
    if group is None:
        raise ValueError("Group not found")

    best_shot_id = group.best_shot_override_photo_id or group.best_shot_photo_id
    if best_shot_id is None:
        raise ValueError("Group has no best shot photo")
    photo = db.get(Photo, best_shot_id)
    if photo is None:
        raise ValueError("Best shot photo not found")

    location_hint = _location_hint_for_photo(db, photo)
    image_bytes = download_bytes(photo.r2_key_medium)

    clear_unreviewed_ai_suggestions(db, [group_id])

    client = get_anthropic_client()
    classification = classify_photo_sync(
        client, image_bytes, "image/webp", location_hint, model=ESCALATION_CLASSIFICATION_MODEL
    )
    _insert_candidates(db, group_id, classification, model=ESCALATION_CLASSIFICATION_MODEL)
    db.flush()
