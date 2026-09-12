import base64
from unittest.mock import MagicMock

from app.classification import (
    SpeciesCandidate,
    SpeciesClassification,
    build_classification_prompt,
    classify_photo_sync,
    image_block,
)


class TestBuildClassificationPrompt:
    def test_no_location_omits_location_clause(self) -> None:
        prompt = build_classification_prompt(None)
        assert "taken in" not in prompt

    def test_includes_location_when_given(self) -> None:
        prompt = build_classification_prompt("Borneo")
        assert "taken in Borneo" in prompt

    def test_mentions_age_and_sex_nuance(self) -> None:
        prompt = build_classification_prompt(None)
        assert "juvenile" in prompt
        assert "female" in prompt and "male" in prompt


def test_image_block_encodes_bytes_and_sets_media_type() -> None:
    block = image_block(b"fake-image-bytes", "image/webp")
    source = block["source"]
    assert block["type"] == "image"
    assert source["type"] == "base64"
    assert source["media_type"] == "image/webp"  # type: ignore[typeddict-item]
    assert base64.standard_b64decode(source["data"]) == b"fake-image-bytes"  # type: ignore[typeddict-item,arg-type]


def test_classify_photo_sync_returns_parsed_output() -> None:
    expected = SpeciesClassification(
        candidates=[SpeciesCandidate(common_name="Eurasian Blue Tit", confidence=0.9)],
    )
    mock_response = MagicMock(parsed_output=expected, stop_reason="end_turn")
    mock_client = MagicMock()
    mock_client.messages.parse.return_value = mock_response

    result = classify_photo_sync(mock_client, b"fake-bytes")

    assert result is expected
    mock_client.messages.parse.assert_called_once()
    call_kwargs = mock_client.messages.parse.call_args.kwargs
    assert call_kwargs["output_format"] is SpeciesClassification
    assert call_kwargs["model"] == "claude-haiku-4-5"


def test_classify_photo_sync_threads_location_hint_into_prompt() -> None:
    mock_response = MagicMock(
        parsed_output=SpeciesClassification(candidates=[]), stop_reason="end_turn"
    )
    mock_client = MagicMock()
    mock_client.messages.parse.return_value = mock_response

    classify_photo_sync(mock_client, b"fake-bytes", location_hint="South Africa")

    call_kwargs = mock_client.messages.parse.call_args.kwargs
    text_block = call_kwargs["messages"][0]["content"][1]
    assert "South Africa" in text_block["text"]


def test_classify_photo_sync_raises_when_unparsed() -> None:
    mock_response = MagicMock(parsed_output=None, stop_reason="refusal")
    mock_client = MagicMock()
    mock_client.messages.parse.return_value = mock_response

    try:
        classify_photo_sync(mock_client, b"fake-bytes")
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "refusal" in str(e)
