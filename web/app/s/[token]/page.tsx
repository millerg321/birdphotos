import { notFound } from "next/navigation";
import Link from "next/link";
import {
  GALLERY_PAGE_SIZE,
  getConfirmedCandidate,
  getGalleryGroups,
  getGalleryGroupsCount,
  getGroupDetail,
  getShareLinkByToken,
  getSpeciesById,
  incrementShareLinkViewCount,
} from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";
import { hasValidGps } from "@/lib/formatExif";
import { GalleryGrid } from "@/components/GalleryGrid";
import { clampPage } from "@/lib/galleryFilters";

// Signed R2 URLs expire — same reasoning as every other page that
// presigns an image (gallery, groups/[id], species/[slug]).
export const dynamic = "force-dynamic";

// Fully public (see plan: Phase 6 — sharing) — proxy.ts/publicPaths.ts
// already treat every /s/* path as public unconditionally, with zero
// token validation at that layer, so this page alone is responsible for
// looking the token up, checking expiry, and 404ing on anything else.
// No auth()/isOwner branching needed: unlike /gallery or /species, there
// is no dual-mode here — everyone who reaches a valid link sees the same
// read-only view.
export default async function SharePage({
  params,
  searchParams,
}: {
  params: Promise<{ token: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const { token } = await params;
  const shareLink = await getShareLinkByToken(token);
  if (!shareLink || (shareLink.expires_at && shareLink.expires_at < new Date())) {
    notFound();
  }

  await incrementShareLinkViewCount(shareLink.id);

  // group/species links always carry a target_id (see getOrCreateShareLink)
  // — a row missing one here would mean a malformed/future link type
  // (e.g. filtered_view, not yet supported) reaching this page.
  if (!shareLink.target_id) {
    notFound();
  }

  if (shareLink.type === "group") {
    return <GroupShareView groupId={shareLink.target_id} />;
  }

  if (shareLink.type === "species") {
    const { page: pageParam } = await searchParams;
    return <SpeciesShareView speciesId={shareLink.target_id} token={token} pageParam={pageParam} />;
  }

  notFound();
}

async function GroupShareView({ groupId }: { groupId: string }) {
  const group = await getGroupDetail(groupId);
  if (!group) {
    notFound();
  }

  const [imageUrl, confirmedCandidate] = await Promise.all([
    getSignedImageUrl(group.mediumKey),
    getConfirmedCandidate(groupId),
  ]);
  const speciesLabel = confirmedCandidate?.commonName ?? confirmedCandidate?.rawLabel ?? "Unreviewed";

  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-10 dark:bg-black">
      <div className="mx-auto max-w-2xl">
        {/* eslint-disable-next-line @next/next/no-img-element -- presigned R2 URL */}
        <img src={imageUrl} alt={speciesLabel} className="w-full rounded-lg object-cover" />
        <h1 className="mt-4 text-2xl font-semibold text-black dark:text-zinc-50">
          {speciesLabel}
        </h1>
        {confirmedCandidate?.scientificName && (
          <p className="italic text-zinc-500">{confirmedCandidate.scientificName}</p>
        )}
        <p className="mt-2 text-sm text-zinc-500">
          {group.takenAt.toLocaleDateString()}
          {group.locationName ? ` · ${group.locationName}` : ""}
        </p>
      </div>
    </main>
  );
}

async function SpeciesShareView({
  speciesId,
  token,
  pageParam,
}: {
  speciesId: string;
  token: string;
  pageParam: string | undefined;
}) {
  const species = await getSpeciesById(speciesId);
  if (!species) {
    notFound();
  }

  const requestedPage = Number.parseInt(pageParam ?? "1", 10);
  const safeRequestedPage = Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  const filterArgs = { speciesSlug: species.slug };
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
      <div className="mb-6">
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
      {/* isOwner=false: this is always an anonymous-shaped view, even
          for the owner's own link, since /s/* never checks auth(). */}
      <GalleryGrid cards={cards} isOwner={false} />
      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-4 text-sm">
          {page > 1 && (
            <Link
              href={`/s/${token}${page - 1 > 1 ? `?page=${page - 1}` : ""}`}
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
              href={`/s/${token}?page=${page + 1}`}
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
