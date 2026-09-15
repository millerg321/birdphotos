import io

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.import_upload import import_from_staged_upload
from app.models import Photo


def _jpeg_bytes() -> bytes:
    arr = np.full((100, 100, 3), 128, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def fake_r2(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """In-memory stand-in for R2 (see the same pattern in
    test_group_bursts.py). Covers both the staging download/cleanup this
    module does directly and the original/thumb/medium uploads that
    import_one_photo does internally via app.jobs.import_photo."""
    store: dict[str, bytes] = {}
    monkeypatch.setattr(
        "app.jobs.import_upload.download_bytes", lambda key: store[key]
    )
    monkeypatch.setattr(
        "app.jobs.import_photo.upload_bytes",
        lambda key, data, content_type: store.__setitem__(key, data),
    )
    deleted: list[str] = []
    monkeypatch.setattr(
        "app.jobs.import_upload.delete_object", lambda key: deleted.append(key)
    )
    store["_deleted"] = deleted  # type: ignore[assignment]
    return store


class TestImportFromStagedUpload:
    def test_imports_a_valid_photo(self, db: Session, fake_r2: dict[str, bytes]) -> None:
        fake_r2["uploads/abc.jpg"] = _jpeg_bytes()

        result = import_from_staged_upload(db, "uploads/abc.jpg")

        assert result.error is None
        assert result.photo_id is not None
        photo = db.execute(
            select(Photo).where(Photo.id == result.photo_id)
        ).scalar_one()
        assert photo.import_source == "manual_upload"

    def test_deletes_the_staging_object_on_success(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        fake_r2["uploads/abc.jpg"] = _jpeg_bytes()

        import_from_staged_upload(db, "uploads/abc.jpg")

        assert "uploads/abc.jpg" in fake_r2["_deleted"]  # type: ignore[operator]

    def test_one_bad_key_reports_an_error_without_raising(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        # Nothing staged at this key — download_bytes raises KeyError.
        result = import_from_staged_upload(db, "uploads/missing.jpg")

        assert result.photo_id is None
        assert result.error is not None

    def test_bad_key_does_not_leave_a_partial_photo_row(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        before = db.execute(select(Photo)).scalars().all()

        import_from_staged_upload(db, "uploads/missing.jpg")

        after = db.execute(select(Photo)).scalars().all()
        assert len(after) == len(before)

    def test_reimporting_the_same_file_is_rejected(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        # Two different staging keys, identical bytes — matches how two
        # separate browser uploads of the same file actually look
        # (getUploadUrlAction mints a fresh random key per upload
        # regardless of content).
        bytes_ = _jpeg_bytes()
        fake_r2["uploads/first.jpg"] = bytes_
        fake_r2["uploads/second.jpg"] = bytes_

        first = import_from_staged_upload(db, "uploads/first.jpg")
        second = import_from_staged_upload(db, "uploads/second.jpg")

        assert first.error is None
        assert second.photo_id is None
        assert second.error is not None
        assert "already" in second.error

        photos = db.execute(select(Photo)).scalars().all()
        assert len(photos) == 1

    def test_different_photos_both_import(
        self, db: Session, fake_r2: dict[str, bytes]
    ) -> None:
        arr_a = np.full((100, 100, 3), 64, dtype=np.uint8)
        buf_a = io.BytesIO()
        Image.fromarray(arr_a).save(buf_a, format="JPEG")
        arr_b = np.full((100, 100, 3), 192, dtype=np.uint8)
        buf_b = io.BytesIO()
        Image.fromarray(arr_b).save(buf_b, format="JPEG")
        fake_r2["uploads/a.jpg"] = buf_a.getvalue()
        fake_r2["uploads/b.jpg"] = buf_b.getvalue()

        first = import_from_staged_upload(db, "uploads/a.jpg")
        second = import_from_staged_upload(db, "uploads/b.jpg")

        assert first.error is None
        assert second.error is None
        assert first.photo_id != second.photo_id
