import Link from "next/link";
import { getSightingsTimeline, getStatsSummary, getTopSpeciesByCount } from "@/lib/db/queries";

// Owner-only (see plan: Phase 5 — stats) — not in lib/publicPaths.ts, so
// the proxy blocks anonymous access the same way /map is. These are
// simple aggregate reads, always current, so no reason to prerender.
export const dynamic = "force-dynamic";

export default async function StatsPage() {
  const [summary, topSpecies, timeline] = await Promise.all([
    getStatsSummary(),
    getTopSpeciesByCount(10),
    getSightingsTimeline(),
  ]);

  const maxSpeciesCount = Math.max(1, ...topSpecies.map((s) => s.sightingCount));
  const maxTimelineCount = Math.max(1, ...timeline.map((t) => t.count));

  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-10 dark:bg-black">
      <h1 className="mb-6 text-2xl font-semibold text-black dark:text-zinc-50">
        Stats
      </h1>

      <div className="mb-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Species" value={summary.totalSpecies} />
        <StatCard label="Photos" value={summary.totalPhotos} />
        <StatCard label="Sightings" value={summary.totalSightings} />
      </div>

      <section className="mb-10">
        <h2 className="mb-3 text-lg font-medium text-black dark:text-zinc-50">
          Most photographed
        </h2>
        {topSpecies.length === 0 ? (
          <p className="text-zinc-500">No confirmed species yet.</p>
        ) : (
          <ul className="space-y-2">
            {topSpecies.map((s) => (
              <li key={s.slug}>
                <Link
                  href={`/species/${s.slug}`}
                  className="flex items-center gap-3 text-sm hover:underline"
                >
                  <span className="w-40 shrink-0 truncate text-black dark:text-zinc-50">
                    {s.commonName}
                  </span>
                  <span className="h-4 flex-1 overflow-hidden rounded bg-zinc-200 dark:bg-zinc-800">
                    <span
                      className="block h-full rounded bg-blue-600"
                      style={{ width: `${(s.sightingCount / maxSpeciesCount) * 100}%` }}
                    />
                  </span>
                  <span className="w-8 shrink-0 text-right text-zinc-500">
                    {s.sightingCount}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium text-black dark:text-zinc-50">
          Timeline
        </h2>
        {timeline.length === 0 ? (
          <p className="text-zinc-500">No sightings yet.</p>
        ) : (
          <ul className="space-y-2">
            {timeline.map((t) => (
              <li key={t.month.toISOString()} className="flex items-center gap-3 text-sm">
                <span className="w-24 shrink-0 text-black dark:text-zinc-50">
                  {t.month.toLocaleDateString(undefined, { month: "short", year: "numeric" })}
                </span>
                <span className="h-4 flex-1 overflow-hidden rounded bg-zinc-200 dark:bg-zinc-800">
                  <span
                    className="block h-full rounded bg-blue-600"
                    style={{ width: `${(t.count / maxTimelineCount) * 100}%` }}
                  />
                </span>
                <span className="w-8 shrink-0 text-right text-zinc-500">{t.count}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-2xl font-semibold text-black dark:text-zinc-50">{value}</p>
      <p className="text-sm text-zinc-500">{label}</p>
    </div>
  );
}
