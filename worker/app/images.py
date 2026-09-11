import io
from dataclasses import dataclass

from PIL import Image, ImageOps

THUMB_LONG_EDGE = 400
MEDIUM_LONG_EDGE = 1600


@dataclass
class Thumbnails:
    thumb: bytes
    medium: bytes


def _resized_webp(img: Image.Image, long_edge: int) -> bytes:
    resized = ImageOps.exif_transpose(img)
    resized.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    resized.convert("RGB").save(buf, format="WEBP", quality=85)
    return buf.getvalue()


def generate_thumbnails(image_bytes: bytes) -> Thumbnails:
    with Image.open(io.BytesIO(image_bytes)) as img:
        thumb = _resized_webp(img, THUMB_LONG_EDGE)
        medium = _resized_webp(img, MEDIUM_LONG_EDGE)
    return Thumbnails(thumb=thumb, medium=medium)
