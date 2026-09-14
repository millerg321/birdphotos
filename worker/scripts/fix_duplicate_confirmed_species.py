"""One-off: reject the stale row wherever a group ended up with more
than one 'confirmed' burst_group_species row.

Root cause: web/lib/db/queries.ts addManualSpecies only rejected
existing pending_review rows before inserting its new confirmed one,
not an existing confirmed row — so manually retyping a species on a
group that already had a confirmed AI suggestion left both confirmed
at once, violating the "at most one confirmed" invariant every other
query assumes. getConfirmedCandidate (no ordering, just
executeTakeFirst()) could non-deterministically show either one;
getGalleryGroups's join instead produced two rows for the same group,
a real duplicate-React-key crash that's what surfaced this. Fixed at
the source in queries.ts; this repairs data written before that fix.

For each affected group, keeps whichever confirmed row has the latest
reviewed_at (matches the DISTINCT ON tiebreak added to
getGalleryGroups) and rejects the rest.

Usage:
    .venv/bin/python -m scripts.fix_duplicate_confirmed_species
"""

from collections import defaultdict

from app.db import SessionLocal
from app.models import BurstGroupSpecies


def main() -> None:
    db = SessionLocal()
    try:
        confirmed = (
            db.query(BurstGroupSpecies)
            .filter(BurstGroupSpecies.status == "confirmed")
            .all()
        )
        by_group: dict[object, list[BurstGroupSpecies]] = defaultdict(list)
        for row in confirmed:
            by_group[row.burst_group_id].append(row)

        fixed = 0
        affected_groups = 0
        for group_id, rows in by_group.items():
            if len(rows) <= 1:
                continue
            affected_groups += 1
            rows.sort(key=lambda r: r.reviewed_at or r.created_at, reverse=True)
            keeper, *stale = rows
            print(f"Group {group_id}: keeping {keeper.id}, rejecting {len(stale)} stale row(s)")
            for row in stale:
                row.status = "rejected"
                fixed += 1

        db.commit()
        print(f"Rejected {fixed} stale confirmed row(s) across {affected_groups} affected group(s)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
