"""One-off: delete redundant pending_review candidate rows where a
group ended up with the same species suggested twice.

Root cause: classify_new_groups_sync (and run_backfill_and_group,
which calls it) had no protection against two concurrent invocations
of POST /jobs/backfill-and-group. _groups_needing_classification's
"already classified" check reads burst_group_species, but nothing
commits until the whole classify pass finishes — so two overlapping
requests (e.g. the "Score, group & classify" button clicked twice
before the first slow request, which makes a real Anthropic API call
per group, returned — now possible from both /upload and /review)
both saw the same groups as unclassified and each inserted a full
set of candidates, doubling them. Confirmed in production: pairs of
rows with identical species_id, the same model_id, near-identical
(not bitwise-equal) confidence — i.e. two independent API calls for
the same photo, not one response inserted twice. Fixed at the source
by an advisory lock around run_backfill_and_group (see app/main.py);
this repairs rows written before that fix.

For each (burst_group_id, species_id) pair with more than one
pending_review row, keeps the earliest (the original run) and deletes
the rest — not a "reject", since these were never a human decision,
just a duplicate of the survivor.

Usage:
    .venv/bin/python -m scripts.fix_duplicate_pending_candidates
"""

from collections import defaultdict

from app.db import SessionLocal
from app.models import BurstGroupSpecies


def main() -> None:
    db = SessionLocal()
    try:
        pending = (
            db.query(BurstGroupSpecies)
            .filter(BurstGroupSpecies.status == "pending_review")
            .all()
        )
        by_group_species: dict[tuple[object, object], list[BurstGroupSpecies]] = defaultdict(list)
        for row in pending:
            by_group_species[(row.burst_group_id, row.species_id)].append(row)

        deleted = 0
        affected_groups: set[object] = set()
        for (group_id, _species_id), rows in by_group_species.items():
            if len(rows) <= 1:
                continue
            affected_groups.add(group_id)
            rows.sort(key=lambda r: r.created_at)
            keeper, *dupes = rows
            print(f"Group {group_id}: keeping {keeper.id}, deleting {len(dupes)} duplicate(s)")
            for row in dupes:
                db.delete(row)
                deleted += 1

        db.commit()
        print(
            f"Deleted {deleted} duplicate pending row(s) "
            f"across {len(affected_groups)} affected group(s)"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
