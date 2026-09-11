"""Phase 3: backfill phash/sharpness/exposure scores, then regroup bursts.

Usage:
    .venv/bin/python -m scripts.backfill_and_group
"""

from app.db import SessionLocal
from app.jobs.group_bursts import backfill_scores, regroup_all


def main() -> None:
    db = SessionLocal()
    try:
        scored = backfill_scores(db)
        db.commit()
        print(f"Scored {scored} photo(s)")

        group_count = regroup_all(db)
        db.commit()
        print(f"Regrouped into {group_count} burst group(s)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
