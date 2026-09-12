import uuid

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Location, Photo

# Rough default for a manually-assigned country/region-level location (see
# plan: Manual Location Fallback) — precision doesn't matter much here since
# the immediate use is the location's `name` as classification context, not
# map display.
DEFAULT_RADIUS_METERS = 500_000

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires a real identifying User-Agent (generic
# or missing ones get blocked) — no API key needed otherwise (see plan:
# Manual Location Fallback). Personal, low-volume, well under their
# 1 req/sec limit.
NOMINATIM_USER_AGENT = "birdphotos-personal-app/1.0"


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


def geocode_place_name(place_name: str) -> tuple[float, float] | None:
    """Looks up a free-text place name via OpenStreetMap Nominatim (free,
    no API key — see plan: Manual Location Fallback). Returns (lat, lng)
    for the best match, or None if nothing matched."""
    response = httpx.get(
        NOMINATIM_URL,
        params={"q": place_name, "format": "json", "limit": 1},
        headers={"User-Agent": NOMINATIM_USER_AGENT},
        timeout=10.0,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])


def set_group_location(db: Session, group_id: uuid.UUID, place_name: str) -> Location:
    """Geocodes place_name and assigns the resulting Location to every
    photo in the group (see plan: Manual Location Fallback). Classification
    uses the best-shot photo's location as context (see plan: AI Species
    Classification — verified to materially change results), and a burst
    is one real-world moment/place, so every photo in it should share the
    same location rather than just the current best shot.

    Raises ValueError if place_name doesn't geocode to anything — the
    caller (the web app) surfaces that back to the user rather than
    silently leaving photos unlocated.
    """
    coords = geocode_place_name(place_name)
    if coords is None:
        raise ValueError(f"Could not find a location matching {place_name!r}")
    lat, lng = coords
    location = get_or_create_location(db, place_name, lat, lng)

    db.execute(
        update(Photo).where(Photo.burst_group_id == group_id).values(location_id=location.id)
    )
    db.flush()
    return location
