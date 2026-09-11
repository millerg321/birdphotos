import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class BurstGroup(Base):
    """Every photo belongs to a group, even a group of one (see plan: Data Model)."""

    __tablename__ = "burst_groups"

    id: Mapped[uuid.UUID] = uuid_pk()
    # use_alter avoids a circular FK dependency at table-creation time, since
    # photos.burst_group_id also points back at this table.
    best_shot_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("photos.id", use_alter=True, name="fk_burst_groups_best_shot"),
    )
    best_shot_override_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("photos.id", use_alter=True, name="fk_burst_groups_best_shot_override"),
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    photos: Mapped[list["Photo"]] = relationship(
        back_populates="burst_group", foreign_keys="Photo.burst_group_id"
    )
    species_candidates: Mapped[list["BurstGroupSpecies"]] = relationship(
        back_populates="burst_group"
    )


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    center_lat: Mapped[float] = mapped_column(nullable=False)
    center_lng: Mapped[float] = mapped_column(nullable=False)
    radius_meters: Mapped[int] = mapped_column(Integer, nullable=False, default=200)


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[uuid.UUID] = uuid_pk()
    burst_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("burst_groups.id"), nullable=False, index=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id")
    )

    google_photos_id: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    import_source: Mapped[str] = mapped_column(String, nullable=False, default="google_photos_api")

    r2_key_original: Mapped[str] = mapped_column(String, nullable=False)
    r2_key_thumb: Mapped[str] = mapped_column(String, nullable=False)
    r2_key_medium: Mapped[str] = mapped_column(String, nullable=False)

    width: Mapped[int | None]
    height: Mapped[int | None]
    taken_at: Mapped[datetime] = mapped_column(nullable=False, index=True)

    camera_make: Mapped[str | None] = mapped_column(String)
    camera_model: Mapped[str | None] = mapped_column(String)
    focal_length_mm: Mapped[float | None]
    aperture: Mapped[float | None]
    iso: Mapped[int | None]
    shutter_speed: Mapped[str | None] = mapped_column(String)

    gps_lat: Mapped[float | None]
    gps_lng: Mapped[float | None]

    phash: Mapped[str | None] = mapped_column(String)
    sharpness_score: Mapped[float | None]
    exposure_score: Mapped[float | None]

    import_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    burst_group: Mapped["BurstGroup"] = relationship(
        back_populates="photos", foreign_keys=[burst_group_id]
    )


class Species(Base):
    __tablename__ = "species"

    id: Mapped[uuid.UUID] = uuid_pk()
    common_name: Mapped[str] = mapped_column(String, nullable=False)
    scientific_name: Mapped[str | None] = mapped_column(String)
    ebird_code: Mapped[str | None] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)


class BurstGroupSpecies(Base):
    """A candidate (AI-suggested or manual) species tag for a burst group.

    A group may have several candidates; at most one should be `confirmed`.
    See app/queries.py `get_effective_species` for how these resolve to
    "the" species for a group.
    """

    __tablename__ = "burst_group_species"

    id: Mapped[uuid.UUID] = uuid_pk()
    burst_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("burst_groups.id"), nullable=False, index=True
    )
    species_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("species.id")
    )

    raw_label: Mapped[str | None] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, nullable=False)  # 'ai_suggested' | 'manual'
    confidence: Mapped[float | None]
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending_review")
    model_id: Mapped[str | None] = mapped_column(String)
    raw_response: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    reviewed_at: Mapped[datetime | None]
    reviewed_by: Mapped[str | None] = mapped_column(String)

    burst_group: Mapped["BurstGroup"] = relationship(back_populates="species_candidates")
    species: Mapped["Species | None"] = relationship()


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)


class BurstGroupTag(Base):
    __tablename__ = "burst_group_tags"
    __table_args__ = (PrimaryKeyConstraint("burst_group_id", "tag_id"),)

    burst_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("burst_groups.id")
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tags.id"))


class ShareLink(Base):
    __tablename__ = "share_links"

    id: Mapped[uuid.UUID] = uuid_pk()
    token: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)  # photo|group|species|filtered_view
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    filter_params: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime | None]
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class IntegrationCredential(Base):
    __tablename__ = "integration_credentials"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. 'google_photos'
    refresh_token: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Job(Base):
    """Postgres-backed background job queue (see plan: Background jobs).

    The worker polls this table with `SELECT ... FOR UPDATE SKIP LOCKED`
    rather than depending on Redis/Celery, matching the plan's deliberately
    simple choice for a personal-scale workload.
    """

    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("job_type", "dedupe_key", name="uq_jobs_type_dedupe"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    job_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error: Mapped[str | None] = mapped_column(String)

    run_after: Mapped[datetime] = mapped_column(server_default=func.now())
    locked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
