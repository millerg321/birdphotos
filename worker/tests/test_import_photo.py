import io
from datetime import datetime

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import delete, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.jobs.import_photo import import_one_photo
from app.models import BurstGroup, Photo


def _jpeg_bytes() -> bytes:
    arr = np.full((100, 100, 3), 128, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def fake_r2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.jobs.import_photo.upload_bytes", lambda key, data, content_type: None
    )


class TestImportOnePhotoDuplicateRace:
    def test_survives_a_concurrent_duplicate_import(
        self, db: Session, db_engine: Engine
    ) -> None:
        """Simulates the race the nested-transaction fallback in
        import_one_photo exists for: another session imports the
        identical file between this call's existence check and its own
        insert. Mirrors test_classify_species.py's
        test_survives_a_concurrent_same_slug_insert exactly — a
        before_flush listener (not patching db.flush directly, which
        also fires on the unrelated autoflush of this function's own
        upfront existence-check SELECT) inserts the "concurrent" row
        only once this call's own Photo with a content_hash is actually
        pending, i.e. right as import_one_photo's nested-transaction
        flush is about to happen — bound to db_engine (the shared
        TEST_DATABASE_URL engine), not app.db.SessionLocal, for the
        same reason as that test: SessionLocal binds to the real
        configured DATABASE_URL, a different database."""
        image_bytes = _jpeg_bytes()
        OtherSession = sessionmaker(bind=db_engine)
        fired = False
        # Unlike the db fixture's own session, "other" commits for real
        # on a separate connection — not rolled back by the db fixture's
        # per-test transaction, so it outlives this test for the rest of
        # the pytest run. _jpeg_bytes() is reused (same bytes, same
        # content_hash) by other tests in this suite, so a leaked row
        # here doesn't just linger harmlessly — it collides with theirs.
        # Tracked and deleted in the finally block below.
        other_ids: dict[str, object] = {}

        def insert_concurrent_row(
            session: Session, flush_context: object, instances: object
        ) -> None:
            nonlocal fired
            if fired:
                return
            pending = [
                obj for obj in session.new if isinstance(obj, Photo) and obj.content_hash
            ]
            if not pending:
                return
            fired = True
            other = OtherSession()
            try:
                other_group = BurstGroup()
                other.add(other_group)
                other.flush()
                other_photo = Photo(
                    burst_group_id=other_group.id,
                    content_hash=pending[0].content_hash,
                    r2_key_original="o",
                    r2_key_thumb="t",
                    r2_key_medium="m",
                    taken_at=datetime.now(),
                )
                other.add(other_photo)
                other.commit()
                other_ids["group_id"] = other_group.id
                other_ids["photo_id"] = other_photo.id
            finally:
                other.close()

        event.listen(db, "before_flush", insert_concurrent_row)
        try:
            with pytest.raises(ValueError, match="already"):
                import_one_photo(
                    db,
                    image_bytes,
                    import_source="manual_upload",
                    fallback_taken_at=datetime.now(),
                )
        finally:
            if event.contains(db, "before_flush", insert_concurrent_row):
                event.remove(db, "before_flush", insert_concurrent_row)
            if "photo_id" in other_ids:
                cleanup = OtherSession()
                try:
                    cleanup.execute(delete(Photo).where(Photo.id == other_ids["photo_id"]))
                    cleanup.execute(
                        delete(BurstGroup).where(BurstGroup.id == other_ids["group_id"])
                    )
                    cleanup.commit()
                finally:
                    cleanup.close()
