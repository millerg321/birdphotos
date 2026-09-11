import io

from PIL import Image

from app.images import MEDIUM_LONG_EDGE, THUMB_LONG_EDGE, generate_thumbnails


def _make_jpeg_bytes(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(120, 180, 90))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_generate_thumbnails_resizes_long_edge() -> None:
    original = _make_jpeg_bytes(4000, 3000)
    result = generate_thumbnails(original)

    thumb = Image.open(io.BytesIO(result.thumb))
    medium = Image.open(io.BytesIO(result.medium))

    assert max(thumb.size) == THUMB_LONG_EDGE
    assert max(medium.size) == MEDIUM_LONG_EDGE
    # Aspect ratio (4:3) preserved
    assert thumb.size[0] / thumb.size[1] == 4000 / 3000


def test_generate_thumbnails_smaller_than_target_not_upscaled() -> None:
    original = _make_jpeg_bytes(200, 150)
    result = generate_thumbnails(original)

    thumb = Image.open(io.BytesIO(result.thumb))
    assert thumb.size == (200, 150)
