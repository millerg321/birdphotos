import io
from dataclasses import dataclass
from datetime import datetime

from PIL import ExifTags, Image

_EXIF_IFD = 0x8769
_GPS_IFD = 0x8825


@dataclass
class PhotoExif:
    taken_at: datetime
    width: int
    height: int
    camera_make: str | None
    camera_model: str | None
    focal_length_mm: float | None
    aperture: float | None
    iso: int | None
    shutter_speed: str | None
    gps_lat: float | None
    gps_lng: float | None


def _as_float(value: object) -> float | None:
    """Pillow returns EXIF rationals as IFDRational, not a plain float —
    psycopg can't adapt that type directly, so coerce at the boundary."""
    return None if value is None else float(value)  # type: ignore[arg-type]


def _gps_to_decimal(coord: tuple, ref: str) -> float | None:
    if not coord or len(coord) != 3:
        return None
    degrees, minutes, seconds = (float(v) for v in coord)
    decimal = degrees + minutes / 60 + seconds / 3600
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


def _shutter_speed_label(exposure_time: float | None) -> str | None:
    if not exposure_time:
        return None
    if exposure_time >= 1:
        return f"{exposure_time:.1f}s"
    return f"1/{round(1 / exposure_time)}s"


def extract_exif(image_bytes: bytes, fallback_taken_at: datetime) -> PhotoExif:
    """Read EXIF from a JPEG's bytes, falling back to file mtime for date.

    Direct FNumber/ExposureTime/ISOSpeedRatings fields are used rather than
    the APEX (ApertureValue/ShutterSpeedValue) tags — verified against real
    sample photos to be present and simpler to interpret directly.
    """
    with Image.open(io.BytesIO(image_bytes)) as img:
        width, height = img.size
        exif = img.getexif()
        basic = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
        detail = {ExifTags.TAGS.get(k, k): v for k, v in exif.get_ifd(_EXIF_IFD).items()}
        gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in exif.get_ifd(_GPS_IFD).items()}

    taken_at_str = detail.get("DateTimeOriginal") or basic.get("DateTime")
    taken_at = fallback_taken_at
    if taken_at_str:
        try:
            taken_at = datetime.strptime(taken_at_str, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            pass

    gps_lat = gps_lng = None
    if "GPSLatitude" in gps and "GPSLongitude" in gps:
        gps_lat = _gps_to_decimal(gps["GPSLatitude"], gps.get("GPSLatitudeRef", "N"))
        gps_lng = _gps_to_decimal(gps["GPSLongitude"], gps.get("GPSLongitudeRef", "E"))

    return PhotoExif(
        taken_at=taken_at,
        width=width,
        height=height,
        camera_make=basic.get("Make"),
        camera_model=basic.get("Model"),
        focal_length_mm=_as_float(detail.get("FocalLength")),
        aperture=_as_float(detail.get("FNumber")),
        iso=detail.get("ISOSpeedRatings") or detail.get("PhotographicSensitivity"),
        shutter_speed=_shutter_speed_label(_as_float(detail.get("ExposureTime"))),
        gps_lat=gps_lat,
        gps_lng=gps_lng,
    )
