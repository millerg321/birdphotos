import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.jobs.classify_species import (
    _groups_needing_classification,
    _slugify,
    get_or_create_species,
    ingest_batch_results,
    submit_batch_classification,
)
from app.models import BurstGroup, BurstGroupSpecies, Photo, Species


def _make_group_with_photo(db: Session) -> BurstGroup:
    group = BurstGroup()
    db.add(group)
    db.flush()
    photo = Photo(
        burst_group_id=group.id,
        r2_key_original="o",
        r2_key_thumb="t",
        r2_key_medium="m",
        taken_at=datetime(2024, 1, 1),
    )
    db.add(photo)
    db.flush()
    group.best_shot_photo_id = photo.id
    db.flush()
    return group


class TestSlugify:
    def test_lowercases_and_hyphenates(self) -> None:
        assert _slugify("Eurasian Blue Tit") == "eurasian-blue-tit"

    def test_strips_punctuation(self) -> None:
        assert _slugify("Ring-necked Parakeet!") == "ring-necked-parakeet"

    def test_empty_input_falls_back(self) -> None:
        assert _slugify("...") == "unknown"


class TestGetOrCreateSpecies:
    def test_creates_new_species(self, db: Session) -> None:
        species = get_or_create_species(db, "Great Spotted Woodpecker", "Dendrocopos major")
        assert species.common_name == "Great Spotted Woodpecker"
        assert species.slug == "great-spotted-woodpecker"

    def test_matches_existing_case_insensitively(self, db: Session) -> None:
        first = get_or_create_species(db, "Great Spotted Woodpecker", None)
        second = get_or_create_species(db, "great spotted woodpecker", None)
        assert first.id == second.id

    def test_different_species_get_different_rows(self, db: Session) -> None:
        a = get_or_create_species(db, "Great Spotted Woodpecker", None)
        b = get_or_create_species(db, "Rose-ringed Parakeet", None)
        assert a.id != b.id


class TestGroupsNeedingClassification:
    def test_excludes_already_classified_groups(self, db: Session) -> None:
        classified = _make_group_with_photo(db)
        unclassified = _make_group_with_photo(db)
        species = get_or_create_species(db, "Barn Owl", None)
        db.add(
            BurstGroupSpecies(
                burst_group_id=classified.id,
                species_id=species.id,
                source="ai_suggested",
                status="pending_review",
                confidence=0.8,
            )
        )
        db.flush()

        pending = _groups_needing_classification(db)
        pending_ids = {g.id for g in pending}
        assert classified.id not in pending_ids
        assert unclassified.id in pending_ids


class TestSubmitBatchClassification:
    def test_returns_none_when_nothing_to_classify(self, db: Session) -> None:
        assert submit_batch_classification(db) is None

    def test_submits_one_request_per_unclassified_group(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_group_with_photo(db)
        _make_group_with_photo(db)

        monkeypatch.setattr(
            "app.jobs.classify_species.download_bytes", lambda key: b"fake-bytes"
        )
        mock_client = MagicMock()
        mock_client.messages.batches.create.return_value = MagicMock(id="batch_123")
        monkeypatch.setattr(
            "app.jobs.classify_species.get_anthropic_client", lambda: mock_client
        )

        batch_id = submit_batch_classification(db)

        assert batch_id == "batch_123"
        call_kwargs = mock_client.messages.batches.create.call_args.kwargs
        assert len(call_kwargs["requests"]) == 2


class TestIngestBatchResults:
    def test_inserts_candidates_for_succeeded_results(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        group = _make_group_with_photo(db)

        classification_json = (
            '{"candidates": [{"common_name": "Barn Owl", '
            '"scientific_name": "Tyto alba", "confidence": 0.87}], "notes": null}'
        )
        succeeded_result = MagicMock(
            custom_id=str(group.id),
            result=MagicMock(
                type="succeeded",
                message=MagicMock(
                    content=[MagicMock(type="text", text=classification_json)]
                ),
            ),
        )
        mock_client = MagicMock()
        mock_client.messages.batches.results.return_value = [succeeded_result]
        monkeypatch.setattr(
            "app.jobs.classify_species.get_anthropic_client", lambda: mock_client
        )

        count = ingest_batch_results(db, "batch_123")

        assert count == 1
        rows = (
            db.query(BurstGroupSpecies)
            .filter(BurstGroupSpecies.burst_group_id == group.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].status == "pending_review"
        assert rows[0].source == "ai_suggested"
        assert rows[0].confidence == 0.87
        species = db.get(Species, rows[0].species_id)
        assert species is not None
        assert species.common_name == "Barn Owl"

    def test_skips_errored_results(self, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
        errored_result = MagicMock(custom_id=str(uuid.uuid4()), result=MagicMock(type="errored"))
        mock_client = MagicMock()
        mock_client.messages.batches.results.return_value = [errored_result]
        monkeypatch.setattr(
            "app.jobs.classify_species.get_anthropic_client", lambda: mock_client
        )

        count = ingest_batch_results(db, "batch_123")
        assert count == 0
