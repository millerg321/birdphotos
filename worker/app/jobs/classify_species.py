import re
import uuid

from anthropic.types import TextBlockParam
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification import (
    CLASSIFICATION_MODEL,
    CLASSIFICATION_PROMPT,
    SpeciesClassification,
    get_anthropic_client,
    image_block,
)
from app.models import BurstGroup, BurstGroupSpecies, Photo, Species
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


def submit_batch_classification(db: Session) -> str | None:
    """One request per burst group (not per photo — see plan: cost
    control by construction), using each group's best-shot medium
    image. Returns None if there's nothing new to classify."""
    groups = _groups_needing_classification(db)
    if not groups:
        return None

    requests = []
    for group in groups:
        best_shot_id = group.best_shot_override_photo_id or group.best_shot_photo_id
        photo = db.get(Photo, best_shot_id)
        assert photo is not None
        image_bytes = download_bytes(photo.r2_key_medium)

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
                                TextBlockParam(type="text", text=CLASSIFICATION_PROMPT),
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
                    model_id=CLASSIFICATION_MODEL,
                    raw_response=classification.model_dump(),
                )
            )
        ingested += 1

    db.flush()
    return ingested
