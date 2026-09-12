import { notFound } from "next/navigation";
import Link from "next/link";
import {
  getAdjacentGroupIds,
  getConfirmedCandidate,
  getGroupDetail,
  getGroupPhotos,
} from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";
import { formatCamera, formatExposure } from "@/lib/formatExif";
import { setBestShotOverrideAction } from "@/lib/actions/setBestShotOverride";
import { reopenForReviewAction } from "@/lib/actions/reviewSpecies";
import { mergeGroupsAction } from "@/lib/actions/mergeGroups";
import { wikipediaSearchUrl } from "@/lib/wikipedia";
import { SubmitButton } from "./SubmitButton";

// See app/gallery/page.tsx — same reasoning (presigned URL expiry, no
// static params here anyway, but explicit is safer than relying on that).
export const dynamic = "force-dynamic";

export default async function GroupDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const group = await getGroupDetail(id);
  if (!group) {
    notFound();
  }

  const photos = await getGroupPhotos(id);
  const [mediumUrl, filmstrip, confirmedCandidate, adjacent] = await Promise.all([
    getSignedImageUrl(group.mediumKey),
    Promise.all(
      photos.map(async (photo) => ({
        ...photo,
        thumbUrl: await getSignedImageUrl(photo.thumbKey),
      })),
    ),
    getConfirmedCandidate(id),
    getAdjacentGroupIds(id, group.takenAt),
  ]);

  const [prevGroupPhotoCount, nextGroupPhotoCount] = await Promise.all([
    adjacent.prevGroupId ? getGroupPhotos(adjacent.prevGroupId).then((p) => p.length) : 0,
    adjacent.nextGroupId ? getGroupPhotos(adjacent.nextGroupId).then((p) => p.length) : 0,
  ]);

  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-10 dark:bg-black">
      <Link href="/gallery" className="text-sm text-zinc-500 hover:underline">
        &larr; Back to gallery
      </Link>

      <div className="mt-4 grid gap-8 md:grid-cols-[2fr_1fr]">
        {/* eslint-disable-next-line @next/next/no-img-element -- presigned R2 URL */}
        <img
          src={mediumUrl}
          alt=""
          className="w-full rounded-lg bg-zinc-100 dark:bg-zinc-900"
        />

        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-zinc-500">Species</dt>
            <dd className="text-black dark:text-zinc-50">
              {confirmedCandidate ? (
                <div className="flex flex-wrap items-center gap-2">
                  <span>
                    {confirmedCandidate.commonName ?? confirmedCandidate.rawLabel ?? "Unknown"}
                    {confirmedCandidate.scientificName && (
                      <span className="text-zinc-500 italic">
                        {" "}
                        — {confirmedCandidate.scientificName}
                      </span>
                    )}
                  </span>
                  <a
                    href={wikipediaSearchUrl(
                      confirmedCandidate.scientificName ??
                        confirmedCandidate.commonName ??
                        confirmedCandidate.rawLabel ??
                        "",
                    )}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                  >
                    Wikipedia ↗
                  </a>
                  <form action={reopenForReviewAction.bind(null, id)}>
                    <button
                      type="submit"
                      className="text-xs text-zinc-500 hover:underline"
                    >
                      Not this? Reopen for review
                    </button>
                  </form>
                </div>
              ) : (
                <Link href="/review" className="text-blue-600 hover:underline dark:text-blue-400">
                  Not yet reviewed
                </Link>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-zinc-500">Taken</dt>
            <dd className="text-black dark:text-zinc-50">
              {group.takenAt.toLocaleString()}
            </dd>
          </div>
          <div>
            <dt className="text-zinc-500">Camera</dt>
            <dd className="text-black dark:text-zinc-50">
              {formatCamera(group.cameraMake, group.cameraModel)}
            </dd>
          </div>
          <div>
            <dt className="text-zinc-500">Focal length</dt>
            <dd className="text-black dark:text-zinc-50">
              {group.focalLengthMm !== null ? `${group.focalLengthMm}mm` : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-zinc-500">Exposure</dt>
            <dd className="text-black dark:text-zinc-50">
              {formatExposure(group.aperture, group.shutterSpeed, group.iso)}
            </dd>
          </div>
          <div>
            <dt className="text-zinc-500">Dimensions</dt>
            <dd className="text-black dark:text-zinc-50">
              {group.width !== null && group.height !== null
                ? `${group.width} × ${group.height}`
                : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-zinc-500">Location</dt>
            <dd className="text-black dark:text-zinc-50">
              {group.gpsLat !== null && group.gpsLng !== null
                ? `${group.gpsLat.toFixed(5)}, ${group.gpsLng.toFixed(5)}`
                : "—"}
            </dd>
          </div>
        </dl>
      </div>

      {filmstrip.length > 1 && (
        <div className="mt-8">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm text-zinc-500">
              {filmstrip.length} photos in this burst
            </h2>
            {group.overridePhotoId !== null && (
              <form action={setBestShotOverrideAction.bind(null, id, null)}>
                <button
                  type="submit"
                  className="text-sm text-zinc-500 hover:underline"
                >
                  Reset to automatic pick
                </button>
              </form>
            )}
          </div>
          <div className="flex gap-3 overflow-x-auto pb-2">
            {filmstrip.map((photo) => {
              const isSelected = photo.photoId === group.photoId;
              return (
                <form
                  key={photo.photoId}
                  action={setBestShotOverrideAction.bind(null, id, photo.photoId)}
                >
                  <button
                    type="submit"
                    disabled={isSelected}
                    className={`overflow-hidden rounded-lg ${
                      isSelected
                        ? "ring-2 ring-blue-500"
                        : "opacity-70 hover:opacity-100"
                    }`}
                    title={isSelected ? "Current best shot" : "Set as best shot"}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element -- presigned R2 URL */}
                    <img
                      src={photo.thumbUrl}
                      alt=""
                      className="h-24 w-24 object-cover"
                    />
                  </button>
                </form>
              );
            })}
          </div>
        </div>
      )}

      {(adjacent.prevGroupId !== null || adjacent.nextGroupId !== null) && (
        <div className="mt-8 border-t border-zinc-200 pt-4 dark:border-zinc-800">
          <h2 className="mb-2 text-sm text-zinc-500">
            Same burst, split apart by grouping?
          </h2>
          <div className="flex flex-wrap gap-2">
            {adjacent.prevGroupId !== null && (
              <form action={mergeGroupsAction.bind(null, id, adjacent.prevGroupId)}>
                <SubmitButton
                  pendingLabel="Merging…"
                  className="rounded-md bg-zinc-200 px-3 py-1.5 text-sm text-black hover:bg-zinc-300 disabled:opacity-50 dark:bg-zinc-800 dark:text-zinc-50 dark:hover:bg-zinc-700"
                >
                  Merge with previous group ({prevGroupPhotoCount} photo
                  {prevGroupPhotoCount === 1 ? "" : "s"})
                </SubmitButton>
              </form>
            )}
            {adjacent.nextGroupId !== null && (
              <form action={mergeGroupsAction.bind(null, id, adjacent.nextGroupId)}>
                <SubmitButton
                  pendingLabel="Merging…"
                  className="rounded-md bg-zinc-200 px-3 py-1.5 text-sm text-black hover:bg-zinc-300 disabled:opacity-50 dark:bg-zinc-800 dark:text-zinc-50 dark:hover:bg-zinc-700"
                >
                  Merge with next group ({nextGroupPhotoCount} photo
                  {nextGroupPhotoCount === 1 ? "" : "s"})
                </SubmitButton>
              </form>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
