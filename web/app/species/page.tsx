import Link from "next/link";
import { getSpeciesIndex } from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";

// Same reasoning as app/gallery/page.tsx — presigned thumbnail URLs
// expire, so this can't be statically prerendered.
export const dynamic = "force-dynamic";

// Public (see plan: Phase 5 — species pages, and lib/publicPaths.ts),
// mirroring /gallery's dual-mode approach — there's nothing owner-only
// to show here (no upload/review affordances belong on a species index),
// so unlike gallery/page.tsx this doesn't need its own auth()/isOwner
// branch at all.
export default async function SpeciesIndexPage() {
  const species = await getSpeciesIndex();
  const cards = await Promise.all(
    species.map(async (s) => ({
      ...s,
      // pg returns count()/bigint results as strings to avoid JS
      // precision loss on large counts — fine everywhere else in this
      // codebase since it's only ever used in arithmetic (which
      // coerces), but the strict === below needs a real number.
      sightingCount: Number(s.sightingCount),
      thumbUrl: s.thumbKey ? await getSignedImageUrl(s.thumbKey) : null,
    })),
  );

  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-10 dark:bg-black">
      <h1 className="mb-6 text-2xl font-semibold text-black dark:text-zinc-50">
        Species
      </h1>
      {cards.length === 0 ? (
        <p className="text-zinc-500">No confirmed species yet.</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {cards.map((s) => (
            <Link
              key={s.slug}
              href={`/species/${s.slug}`}
              className="group overflow-hidden rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950"
            >
              <div className="aspect-square w-full overflow-hidden bg-zinc-200 dark:bg-zinc-800">
                {s.thumbUrl && (
                  // eslint-disable-next-line @next/next/no-img-element -- signed R2 URLs, not a static/optimizable asset
                  <img
                    src={s.thumbUrl}
                    alt={s.commonName}
                    className="h-full w-full object-cover transition group-hover:scale-105"
                  />
                )}
              </div>
              <div className="p-2">
                <p className="text-sm font-medium text-black dark:text-zinc-50">
                  {s.commonName}
                </p>
                {s.scientificName && (
                  <p className="text-xs italic text-zinc-500">{s.scientificName}</p>
                )}
                <p className="text-xs text-zinc-500">
                  {s.sightingCount} sighting{s.sightingCount === 1 ? "" : "s"}
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
