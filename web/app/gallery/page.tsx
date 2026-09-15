import Link from "next/link";
import {
  getConfirmedSpeciesList,
  getGalleryGroups,
  getUnreviewedGalleryCount,
} from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";
import { hasValidGps } from "@/lib/formatExif";
import { auth } from "@/lib/auth";
import { GalleryFilterBar } from "@/components/GalleryFilterBar";
import { GalleryGrid } from "@/components/GalleryGrid";
import { buildFilterUrl } from "@/lib/galleryFilters";

// Next can't see the DB query or presigned-URL generation as "dynamic"
// data (neither is a fetch() call), so without this it gets prerendered
// once at build time — freezing the photo list and baking in R2 URLs
// that expire within the hour. Force per-request rendering instead.
export const dynamic = "force-dynamic";

// Public (see plan: ephemeral photo identification — /gallery is in
// lib/publicPaths.ts's allow-list, so the proxy lets anonymous requests
// reach this page at all) but dual-mode: this is the one page in the
// app that renders differently rather than being all-or-nothing behind
// auth, so it calls auth() itself. Anonymous visitors get thumbnail +
// species + date only — no "Needs review" workflow affordance, no
// upload link, no location-management badge. Clicking a card still
// links to /groups/[id] either way; an anonymous visitor just gets
// bounced to /login by the proxy's normal gate, same as hitting any
// other protected URL directly.
const SORT_OPTIONS = ["newest", "oldest", "sharpest", "most-photos"] as const;
type SortOption = (typeof SORT_OPTIONS)[number];
function isSortOption(value: string | undefined): value is SortOption {
  return !!value && (SORT_OPTIONS as readonly string[]).includes(value);
}

export default async function GalleryPage({
  searchParams,
}: {
  searchParams: Promise<{
    filter?: string;
    species?: string;
    from?: string;
    to?: string;
    sort?: string;
  }>;
}) {
  const session = await auth();
  const isOwner = !!session?.user?.email;

  const params = await searchParams;
  const isUnreviewedFilter = isOwner && params.filter === "unreviewed";
  const sort = isSortOption(params.sort) ? params.sort : undefined;
  const currentFilters = {
    filter: isUnreviewedFilter ? "unreviewed" : null,
    species: params.species ?? null,
    from: params.from ?? null,
    to: params.to ?? null,
    sort: sort ?? null,
  };
  const hasActiveFilter = !!(currentFilters.species || currentFilters.from || currentFilters.to);

  const [groups, unreviewedCount, speciesList] = await Promise.all([
    getGalleryGroups({
      unreviewed: isUnreviewedFilter,
      speciesSlug: params.species,
      from: params.from,
      to: params.to,
      sort,
    }),
    isOwner ? getUnreviewedGalleryCount() : Promise.resolve(0),
    getConfirmedSpeciesList(),
  ]);
  const cards = await Promise.all(
    groups.map(async (group) => ({
      groupId: group.groupId,
      thumbUrl: await getSignedImageUrl(group.thumbKey),
      speciesLabel: group.speciesCommonName ?? group.speciesRawLabel ?? "Unreviewed",
      // The correlated COUNT subquery is typed nullable by Kysely, but
      // can't actually be null/0 in practice — the group's own best
      // shot photo always counts as at least one row.
      photoCount: group.photoCount ?? 1,
      isMissingLocation: !hasValidGps(group.gpsLat, group.gpsLng) && group.locationName === null,
    })),
  );

  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-10 dark:bg-black">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
          Gallery
        </h1>
        {isOwner && (
          <Link
            href="/upload"
            className="text-sm text-blue-600 hover:underline dark:text-blue-400"
          >
            Upload photos
          </Link>
        )}
      </div>
      {isOwner && (
        <div className="mb-4 flex gap-4 text-sm">
          <Link
            href={buildFilterUrl(currentFilters, { filter: null })}
            className={
              isUnreviewedFilter
                ? "text-zinc-500 hover:text-black dark:hover:text-zinc-50"
                : "font-medium text-black dark:text-zinc-50"
            }
          >
            All
          </Link>
          <Link
            href={buildFilterUrl(currentFilters, { filter: "unreviewed" })}
            className={
              isUnreviewedFilter
                ? "font-medium text-black dark:text-zinc-50"
                : "text-zinc-500 hover:text-black dark:hover:text-zinc-50"
            }
          >
            Needs review{unreviewedCount > 0 ? ` (${unreviewedCount})` : ""}
          </Link>
        </div>
      )}
      <GalleryFilterBar species={speciesList} current={currentFilters} />
      <GalleryGrid cards={cards} isOwner={isOwner} />
      {cards.length === 0 && (
        <p className="text-zinc-500">
          {hasActiveFilter
            ? "No photos match these filters."
            : isUnreviewedFilter
              ? "Nothing needs review."
              : "No photos yet."}
        </p>
      )}
    </main>
  );
}
