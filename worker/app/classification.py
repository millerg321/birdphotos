import base64
from typing import Literal

import anthropic
from anthropic.types import ImageBlockParam, TextBlockParam
from pydantic import BaseModel, Field

from app.config import settings

# claude-haiku-4-5 per the plan's cost target (see plan: AI Species
# Classification) — vision-capable, cheap enough for a large personal
# photo backlog; swappable to claude-sonnet-5 later for a low-confidence
# re-check pass without touching callers.
CLASSIFICATION_MODEL = "claude-haiku-4-5"

CLASSIFICATION_PROMPT = (
    "You are helping identify the bird species in this photo for a personal "
    "birding photo collection. Give up to 3 candidate species, ranked by "
    "confidence. If you cannot identify a bird in the photo at all, return "
    "an empty candidates list rather than guessing."
)


class SpeciesCandidate(BaseModel):
    common_name: str
    scientific_name: str | None = None
    confidence: float = Field(ge=0, le=1)


class SpeciesClassification(BaseModel):
    candidates: list[SpeciesCandidate] = Field(max_length=3)
    notes: str | None = None


def get_anthropic_client() -> anthropic.Anthropic:
    """pydantic-settings loads .env into `settings` but does not mutate
    os.environ, so the SDK's zero-arg env-var resolution won't see
    ANTHROPIC_API_KEY locally even though it's in .env (Fly.io secrets
    *are* real process env vars, so this only matters for local dev —
    but passing it explicitly is correct in both cases)."""
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def image_block(
    image_bytes: bytes,
    media_type: Literal["image/jpeg", "image/png", "image/gif", "image/webp"],
) -> ImageBlockParam:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
        },
    }


def classify_photo_sync(
    client: anthropic.Anthropic,
    image_bytes: bytes,
    media_type: Literal["image/jpeg", "image/png", "image/gif", "image/webp"] = "image/webp",
) -> SpeciesClassification:
    """Synchronous single-photo classification — used for the incremental
    path (new imports going forward, see plan). The bulk backlog path
    uses the Batch API instead (see app/jobs/classify_species.py), which
    doesn't support client.messages.parse()'s convenience wrapper, so
    that path builds the same schema as a raw json_schema instead."""
    response = client.messages.parse(
        model=CLASSIFICATION_MODEL,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    image_block(image_bytes, media_type),
                    TextBlockParam(type="text", text=CLASSIFICATION_PROMPT),
                ],
            }
        ],
        output_format=SpeciesClassification,
    )
    if response.parsed_output is None:
        raise ValueError(f"Classification did not parse (stop_reason={response.stop_reason})")
    return response.parsed_output
