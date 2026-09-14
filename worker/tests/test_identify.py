from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.classification import (
    ESCALATION_CLASSIFICATION_MODEL,
    SpeciesCandidate,
    SpeciesClassification,
)
from app.config import settings
from app.main import app

client = TestClient(app)


def test_identify_requires_internal_token() -> None:
    response = client.post("/identify", files={"file": ("photo.jpg", b"fake", "image/jpeg")})
    assert response.status_code == 401


def test_identify_returns_candidates_without_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No db fixture involved at all here, deliberately — /identify has no
    # `db` dependency (see app/main.py), so there is structurally nothing
    # for this request to persist to Photo/BurstGroup/Species; this test
    # only needs to prove the classification call itself round-trips.
    expected = SpeciesClassification(
        candidates=[SpeciesCandidate(common_name="Eurasian Blue Tit", confidence=0.9)],
    )
    mock_response = MagicMock(parsed_output=expected, stop_reason="end_turn")
    mock_client = MagicMock()
    mock_client.messages.parse.return_value = mock_response
    monkeypatch.setattr("app.main.get_anthropic_client", lambda: mock_client)

    response = client.post(
        "/identify",
        headers={"X-Internal-Token": settings.internal_api_token},
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    call_kwargs = mock_client.messages.parse.call_args.kwargs
    image_source = call_kwargs["messages"][0]["content"][0]["source"]
    assert image_source["media_type"] == "image/jpeg"
    # The one classification path a stranger's single result actually
    # gets to see — worth Sonnet's higher cost over the Haiku default
    # used everywhere else (see app/main.py identify_photo docstring).
    assert call_kwargs["model"] == ESCALATION_CLASSIFICATION_MODEL


def test_identify_threads_location_hint_into_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock(
        parsed_output=SpeciesClassification(candidates=[]), stop_reason="end_turn"
    )
    mock_client = MagicMock()
    mock_client.messages.parse.return_value = mock_response
    monkeypatch.setattr("app.main.get_anthropic_client", lambda: mock_client)

    response = client.post(
        "/identify",
        headers={"X-Internal-Token": settings.internal_api_token},
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        data={"location_hint": "  South Africa  "},
    )

    assert response.status_code == 200
    call_kwargs = mock_client.messages.parse.call_args.kwargs
    text_block = call_kwargs["messages"][0]["content"][1]
    assert "South Africa" in text_block["text"]


def test_identify_truncates_an_overlong_location_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock(
        parsed_output=SpeciesClassification(candidates=[]), stop_reason="end_turn"
    )
    mock_client = MagicMock()
    mock_client.messages.parse.return_value = mock_response
    monkeypatch.setattr("app.main.get_anthropic_client", lambda: mock_client)

    response = client.post(
        "/identify",
        headers={"X-Internal-Token": settings.internal_api_token},
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        data={"location_hint": "x" * 500},
    )

    assert response.status_code == 200
    call_kwargs = mock_client.messages.parse.call_args.kwargs
    text_block = call_kwargs["messages"][0]["content"][1]
    assert "x" * 200 in text_block["text"]
    assert "x" * 201 not in text_block["text"]
