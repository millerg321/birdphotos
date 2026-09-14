"""Tests for the Postgres advisory lock in POST /jobs/backfill-and-group
(app/main.py run_backfill_and_group) — guards against the concurrent-
request race that let a group get classified twice (see that
function's docstring, and scripts/fix_duplicate_pending_candidates.py
for the production repair this was written for).

Exercises the raw SQL on two independent connections rather than
through the FastAPI endpoint or the db fixture's savepoint-wrapped
session: the endpoint's own dependencies (Anthropic API, R2) aren't
mocked in this suite, and advisory locks aren't transactional, so a
savepoint doesn't isolate them the way it does ordinary row data —
two real connections is what actually reproduces two overlapping
requests each on their own connection, which is the scenario being
guarded against.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.main import _BACKFILL_AND_GROUP_LOCK_KEY


def test_second_concurrent_lock_attempt_fails(db_engine: Engine) -> None:
    conn_a = db_engine.connect()
    conn_b = db_engine.connect()
    try:
        got_a = conn_a.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": _BACKFILL_AND_GROUP_LOCK_KEY}
        ).scalar()
        assert got_a is True

        got_b = conn_b.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": _BACKFILL_AND_GROUP_LOCK_KEY}
        ).scalar()
        assert got_b is False
    finally:
        conn_a.execute(text("SELECT pg_advisory_unlock_all()"))
        conn_b.execute(text("SELECT pg_advisory_unlock_all()"))
        conn_a.close()
        conn_b.close()


def test_unlock_all_releases_the_lock_for_reuse(db_engine: Engine) -> None:
    conn_a = db_engine.connect()
    try:
        acquired = conn_a.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": _BACKFILL_AND_GROUP_LOCK_KEY}
        ).scalar()
        assert acquired is True
        conn_a.execute(text("SELECT pg_advisory_unlock_all()"))
    finally:
        conn_a.close()

    # Simulates the pooling gotcha the run_backfill_and_group docstring
    # warns about: without unlock_all, a lock left on a connection
    # returned to the pool would make the next request to reuse that
    # same physical connection trivially "succeed" at acquiring a lock
    # someone else still holds, silently defeating the guard.
    conn_b = db_engine.connect()
    try:
        reacquired = conn_b.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": _BACKFILL_AND_GROUP_LOCK_KEY}
        ).scalar()
        assert reacquired is True
    finally:
        conn_b.execute(text("SELECT pg_advisory_unlock_all()"))
        conn_b.close()
