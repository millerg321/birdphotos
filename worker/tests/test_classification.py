import base64
from unittest.mock import MagicMock

from app.classification import (
    SpeciesCandidate,
    SpeciesClassification,
    classify_photo_sync,
    image_block,
)


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


def test_classify_photo_sync_raises_when_unparsed() -> None:
    mock_response = MagicMock(parsed_output=None, stop_reason="refusal")
    mock_client = MagicMock()
    mock_client.messages.parse.return_value = mock_response

    try:
        classify_photo_sync(mock_client, b"fake-bytes")
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "refusal" in str(e)
