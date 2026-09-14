"""One-off: null out any gps_lat/gps_lng that ended up as NaN.

Root cause: a malformed 0/0 GPS EXIF rational (some cameras/apps write
this when location was unavailable, rather than omitting the tag)
comes back from Pillow's IFDRational as nan rather than raising or
returning None — see app/exif_utils.py _gps_to_decimal, fixed there
for new imports going forward. NaN isn't SQL NULL or JS null, so it
silently broke the group detail page's "no GPS, show the manual
location override" check for at least one already-imported photo.
This repairs photos imported before that fix.

Usage:
    .venv/bin/python -m scripts.fix_nan_gps
"""

import math

from app.db import SessionLocal
from app.models import Photo


def main() -> None:
    db = SessionLocal()
    try:
        fixed = 0
        for photo in db.query(Photo).all():
            has_nan = (photo.gps_lat is not None and math.isnan(photo.gps_lat)) or (
                photo.gps_lng is not None and math.isnan(photo.gps_lng)
            )
            if has_nan:
                print(f"Fixing {photo.id} (was {photo.gps_lat}, {photo.gps_lng})")
                photo.gps_lat = None
                photo.gps_lng = None
                fixed += 1
        db.commit()
        print(f"Fixed {fixed} photo(s) with NaN GPS coordinates")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
