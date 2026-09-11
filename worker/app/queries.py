import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BurstGroupSpecies


def get_effective_species(db: Session, burst_group_id: uuid.UUID) -> BurstGroupSpecies | None:
    """Return "the" species candidate for a group, or None if unresolved.

    A `confirmed` row always wins if present. Otherwise, when AI suggestions
    are trusted (`settings.trust_ai_suggestions` — see plan: Data Model),
    the highest-confidence `pending_review` candidate is returned instead.
    """
    statuses = ["confirmed"] + (["pending_review"] if settings.trust_ai_suggestions else [])
    stmt = (
        select(BurstGroupSpecies)
        .where(
            BurstGroupSpecies.burst_group_id == burst_group_id,
            BurstGroupSpecies.status.in_(statuses),
        )
        .order_by(
            # confirmed rows first, then by confidence
            (BurstGroupSpecies.status == "confirmed").desc(),
            BurstGroupSpecies.confidence.desc().nullslast(),
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def effective_best_shot_photo_id(burst_group) -> uuid.UUID | None:  # type: ignore[no-untyped-def]
    """COALESCE(override, computed) — override always wins (see plan)."""
    return burst_group.best_shot_override_photo_id or burst_group.best_shot_photo_id
