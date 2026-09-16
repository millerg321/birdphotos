import { getMapSightings } from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";
import { hasValidGps } from "@/lib/formatExif";
import { MapView } from "@/components/MapView";

// Same reasoning as app/gallery/page.tsx — presigned thumbnail URLs
// expire, so this can't be statically prerendered.
export const dynamic = "force-dynamic";

// Owner-only (see plan: Phase 5 — map; GPS pins are more sensitive than
// a species field guide, e.g. nesting-site locations) — not in
// lib/publicPaths.ts, so the proxy blocks anonymous access the same way
// /groups/[id] is protected today. No explicit auth()/isOwner branch
// needed here for the same reason that page has none.
export default async function MapPage() {
  const sightings = await getMapSightings();
  const points = await Promise.all(
    sightings
      // The SQL "is not null" filter in getMapSightings doesn't catch
      // the known NaN-GPS quirk (see hasValidGps's own comment) — same
      // check app/gallery/page.tsx already applies to the same fields.
      .filter((s) => hasValidGps(s.gpsLat, s.gpsLng))
      .map(async (s) => ({
        groupId: s.groupId,
        thumbUrl: await getSignedImageUrl(s.thumbKey),
        speciesLabel: s.speciesCommonName ?? s.speciesRawLabel ?? "Unreviewed",
        gpsLat: s.gpsLat as number,
        gpsLng: s.gpsLng as number,
      })),
  );

  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-10 dark:bg-black">
      <h1 className="mb-6 text-2xl font-semibold text-black dark:text-zinc-50">
        Map
      </h1>
      {points.length === 0 ? (
        <p className="text-zinc-500">No GPS-tagged sightings yet.</p>
      ) : (
        <MapView sightings={points} />
      )}
    </main>
  );
}
