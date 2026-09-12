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
    store: dict[str, bytes] = {}
    monkeypatch.setattr(
        "app.jobs.import_upload.download_bytes", lambda key: store[key]
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
