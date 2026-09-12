"""One-off: assign locations to the 11 test-set burst groups based on
where the user said each was actually taken, then reclassify with that
location context (see plan: AI Species Classification — location
materially changes results, verified against real misclassifications
that skewed toward North American species with no location context).

Groups are matched by their best-shot photo's taken_at, not by a
hardcoded group ID: local dev and production are separate databases
populated by separate import runs, so the same photo gets a different
burst_group UUID in each — taken_at is the one thing that's actually
stable across environments here (same source photos, same EXIF).
Hardcoding local dev's UUIDs the first time round silently matched
zero groups in production ("Nothing to reclassify") — no error, since
an empty group_ids filter is a legitimate result, not a bug by itself.

Usage:
    .venv/bin/python -m scripts.assign_test_locations
"""

import time
from datetime import datetime

from app.classification import get_anthropic_client
from app.db import SessionLocal
from app.jobs.classify_species import (
    clear_unreviewed_ai_suggestions,
    ingest_batch_results,
    submit_batch_classification,
)
from app.locations import get_or_create_location
from app.models import BurstGroup, Photo

LOCATIONS = {
    "London, UK": (51.5074, -0.1278),
    "Ireland": (53.1424, -7.6921),
    "Borneo": (0.9619, 114.5548),
    "South Africa": (-30.5595, 22.9375),
}

# Confirmed with the user by viewing each photo directly (see conversation).
# Keyed by the best-shot photo's taken_at (see module docstring).
TAKEN_AT_LOCATIONS: dict[datetime, str] = {
    datetime(2024, 2, 12, 7, 30, 6): "London, UK",  # woodpecker
    datetime(2024, 2, 12, 7, 28, 17): "London, UK",  # parakeet, nest hole
    datetime(2021, 2, 9, 11, 19, 58): "London, UK",  # parakeets + crow
    datetime(2023, 4, 19, 13, 59, 44): "Ireland",  # loon
    datetime(2022, 5, 30, 13, 23, 20): "Ireland",  # juvenile wagtail
    datetime(2019, 11, 14, 19, 21, 51): "Borneo",  # kingfisher
    datetime(2019, 11, 14, 20, 36, 56): "Borneo",  # owl
    datetime(2019, 11, 25, 3, 34, 34): "Borneo",  # dark blue/black bird
    # Chestnut bird, tall grass — corrected: Borneo, not South Africa
    datetime(2019, 11, 12, 8, 24, 19): "Borneo",
    datetime(2017, 9, 30, 11, 11, 52): "South Africa",  # penguins
    datetime(2017, 9, 23, 8, 12, 16): "South Africa",  # chestnut bird, dry grass
}

POLL_INTERVAL_SECONDS = 5


def main() -> None:
    db = SessionLocal()
    try:
        location_rows = {
            name: get_or_create_location(db, name, lat, lng)
            for name, (lat, lng) in LOCATIONS.items()
        }
        db.commit()

        groups_by_taken_at = {
            photo.taken_at: group
            for group, photo in db.query(BurstGroup, Photo)
            .join(Photo, Photo.id == BurstGroup.best_shot_photo_id)
            .all()
        }

        group_ids = []
        for taken_at, location_name in TAKEN_AT_LOCATIONS.items():
            group = groups_by_taken_at.get(taken_at)
            if group is None:
                print(f"WARNING: no group found for taken_at={taken_at}, skipping")
                continue
            location = location_rows[location_name]
            db.query(Photo).filter(Photo.burst_group_id == group.id).update(
                {"location_id": location.id}
            )
            group_ids.append(group.id)
        db.commit()
        print(f"Assigned locations to {len(group_ids)} groups")

        clear_unreviewed_ai_suggestions(db, group_ids)
        db.commit()
        print("Cleared old unreviewed AI suggestions for these groups")

        batch_id = submit_batch_classification(db, group_ids=group_ids)
        db.commit()
        if batch_id is None:
            print("Nothing to reclassify.")
            return
        print(f"Submitted batch {batch_id}")

        client = get_anthropic_client()
        while True:
            batch = client.messages.batches.retrieve(batch_id)
            print(f"Status: {batch.processing_status}")
            if batch.processing_status == "ended":
                break
            time.sleep(POLL_INTERVAL_SECONDS)

        counts = batch.request_counts
        print(f"Succeeded: {counts.succeeded}, errored: {counts.errored}")

        count = ingest_batch_results(db, batch_id)
        db.commit()
        print(f"Ingested classifications for {count} group(s)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
