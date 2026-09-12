from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Location

# Rough default for a manually-assigned country/region-level location (see
# plan: Manual Location Fallback) — precision doesn't matter much here since
# the immediate use is the location's `name` as classification context, not
# map display.
DEFAULT_RADIUS_METERS = 500_000


def get_or_create_location(
    db: Session,
    name: str,
    center_lat: float,
    center_lng: float,
    radius_meters: int = DEFAULT_RADIUS_METERS,
) -> Location:
    existing = db.execute(
        select(Location).where(Location.name.ilike(name))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    location = Location(
        name=name, center_lat=center_lat, center_lng=center_lng, radius_meters=radius_meters
    )
    db.add(location)
    db.flush()
    return location
