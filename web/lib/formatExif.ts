export function formatExposure(
  aperture: number | null,
  shutterSpeed: string | null,
  iso: number | null,
): string {
  const parts = [
    aperture !== null ? `f/${aperture}` : null,
    shutterSpeed,
    iso !== null ? `ISO ${iso}` : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : "—";
}

// Many cameras' EXIF Model already includes the Make (e.g. "Canon
// PowerShot SX740 HS"), so a naive `${make} ${model}` join duplicates it.
export function formatCamera(make: string | null, model: string | null): string {
  if (model?.toLowerCase().startsWith(make?.toLowerCase() ?? "\0")) {
    return model;
  }
  return [make, model].filter(Boolean).join(" ") || "—";
}

// Guards against a data quirk, not just a hypothetical: some cameras/
// apps write a literal 0/0 GPS rational when location was unavailable
// rather than omitting the tag, and Pillow silently turns that into NaN
// instead of raising (see worker/app/exif_utils.py _gps_to_decimal,
// fixed there for new imports going forward). NaN survived into
// Postgres for at least one already-imported photo — it's neither SQL
// NULL nor JS null, so treat it explicitly as "no real GPS" everywhere
// this is checked, or a NaN-afflicted photo looks like it has real
// coordinates instead of needing the manual location override.
export function hasValidGps(lat: number | null, lng: number | null): boolean {
  return lat !== null && lng !== null && !Number.isNaN(lat) && !Number.isNaN(lng);
}
