import Link from "next/link";
import { notFound } from "next/navigation";
import {
  GALLERY_PAGE_SIZE,
  getGalleryGroups,
  getGalleryGroupsCount,
  getSpeciesBySlug,
} from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";
import { hasValidGps } from "@/lib/formatExif";
import { auth } from "@/lib/auth";
import { GalleryGrid } from "@/components/GalleryGrid";
import { ShareButton } from "@/components/ShareButton";
import { clampPage } from "@/lib/galleryFilters";

// Same reasoning as app/gallery/page.tsx — presigned thumbnail URLs
// expire, so this can't be statically prerendered.
export const dynamic = "force-dynamic";

// Public (see plan: Phase 5 — species pages), same dual-mode approach as
// /gallery: isOwner just gates GalleryGrid's owner-only badges/actions,
// same component this page reuses for its sighting-history grid.
export default async function SpeciesDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const { slug } = await params;
  const species = await getSpeciesBySlug(slug);
  if (!species) {
    notFound();
  }

  const session = await auth();
  const isOwner = !!session?.user?.email;

  const { page: pageParam } = await searchParams;
  const requestedPage = Number.parseInt(pageParam ?? "1", 10);
  const safeRequestedPage = Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  const filterArgs = { speciesSlug: slug };
  // pg returns count()/bigint results as strings (avoids JS precision
  // loss on large counts) — harmless in the Math.ceil below (numeric
  // strings coerce fine in arithmetic), but the sightingCount === 1
  // pluralization check further down needs a real number.
  const groupsCount = Number(await getGalleryGroupsCount(filterArgs));
  const totalPages = Math.max(1, Math.ceil(groupsCount / GALLERY_PAGE_SIZE));
  const page = clampPage(safeRequestedPage, totalPages);

  const groups = await getGalleryGroups(filterArgs, page);
  const cards = await Promise.all(
    groups.map(async (group) => ({
      groupId: group.groupId,
      thumbUrl: await getSignedImageUrl(group.thumbKey),
      speciesLabel: group.speciesCommonName ?? group.speciesRawLabel ?? "Unreviewed",
      photoCount: group.photoCount ?? 1,
      isMissingLocation: !hasValidGps(group.gpsLat, group.gpsLng) && group.locationName === null,
    })),
  );

  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-10 dark:bg-black">
      <Link href="/species" className="text-sm text-zinc-500 hover:underline">
        &larr; Back to species
      </Link>
      <div className="mb-6 mt-2 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
            {species.common_name}
          </h1>
          {species.scientific_name && (
            <p className="italic text-zinc-500">{species.scientific_name}</p>
          )}
          <p className="text-sm text-zinc-500">
            {groupsCount} sighting{groupsCount === 1 ? "" : "s"}
          </p>
        </div>
        {/* Anonymous visitors can view this page (it's public) but
            can't mint a link — createShareLinkAction requires a
            session, so the button itself stays owner-only. */}
        {isOwner && <ShareButton type="species" targetId={species.id} />}
      </div>
      <GalleryGrid cards={cards} isOwner={isOwner} />
      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-4 text-sm">
          {page > 1 && (
            <Link
              href={`/species/${slug}${page - 1 > 1 ? `?page=${page - 1}` : ""}`}
              className="text-blue-600 hover:underline dark:text-blue-400"
            >
              ← Previous
            </Link>
          )}
          <span className="text-zinc-500">
            Page {page} of {totalPages}
          </span>
          {page < totalPages && (
            <Link
              href={`/species/${slug}?page=${page + 1}`}
              className="text-blue-600 hover:underline dark:text-blue-400"
            >
              Next →
            </Link>
          )}
        </div>
      )}
    </main>
  );
}
