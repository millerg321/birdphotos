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
