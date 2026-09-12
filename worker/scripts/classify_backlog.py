"""Phase 4: submit the AI species classification batch for every
burst group that doesn't have one yet, poll until done, then ingest
results into burst_group_species (status='pending_review').

Usage:
    .venv/bin/python -m scripts.classify_backlog
"""

import time

from app.classification import get_anthropic_client
from app.db import SessionLocal
from app.jobs.classify_species import ingest_batch_results, submit_batch_classification

POLL_INTERVAL_SECONDS = 5


def main() -> None:
    db = SessionLocal()
    try:
        batch_id = submit_batch_classification(db)
        db.commit()
        if batch_id is None:
            print("Nothing to classify.")
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
