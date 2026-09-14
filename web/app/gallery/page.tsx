import Link from "next/link";
import { getGalleryGroups } from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";
import { hasValidGps } from "@/lib/formatExif";

// Next can't see the DB query or presigned-URL generation as "dynamic"
// data (neither is a fetch() call), so without this it gets prerendered
// once at build time — freezing the photo list and baking in R2 URLs
// that expire within the hour. Force per-request rendering instead.
export const dynamic = "force-dynamic";

export default async function GalleryPage() {
  const groups = await getGalleryGroups();
  const cards = await Promise.all(
    groups.map(async (group) => ({
      ...group,
      thumbUrl: await getSignedImageUrl(group.thumbKey),
    })),
  );

  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-10 dark:bg-black">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
          Gallery
        </h1>
        <Link
          href="/upload"
          className="text-sm text-blue-600 hover:underline dark:text-blue-400"
        >
          Upload photos
        </Link>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        {cards.map((card) => {
          const speciesLabel = card.speciesCommonName ?? card.speciesRawLabel ?? "Unreviewed";
          const isMissingLocation =
            !hasValidGps(card.gpsLat, card.gpsLng) && card.locationName === null;
          // The correlated COUNT subquery is typed nullable by Kysely, but
          // can't actually be null/0 in practice — the group's own best
          // shot photo always counts as at least one row.
          const photoCount = card.photoCount ?? 1;
          return (
            <Link
              key={card.groupId}
              href={`/groups/${card.groupId}`}
              className="group relative overflow-hidden rounded-lg bg-zinc-100 dark:bg-zinc-900"
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- presigned R2 URLs, not a static/known-domain source Next/Image can optimize */}
              <img
                src={card.thumbUrl}
                alt=""
                className="aspect-square w-full object-cover transition-opacity group-hover:opacity-80"
              />

              {photoCount > 1 && (
                <span className="absolute top-1.5 right-1.5 rounded-full bg-black/70 px-1.5 py-0.5 text-xs font-medium text-white">
                  ×{photoCount}
                </span>
              )}

              {isMissingLocation && (
                <span className="absolute top-1.5 left-1.5 rounded-full bg-amber-600/90 px-1.5 py-0.5 text-xs font-medium text-white">
                  No location
                </span>
              )}

              <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/80 to-transparent px-2 py-1.5 text-xs text-white">
                {speciesLabel}
              </span>
            </Link>
          );
        })}
      </div>
      {cards.length === 0 && (
        <p className="text-zinc-500">No photos yet.</p>
      )}
    </main>
  );
}
