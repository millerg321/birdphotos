import { notFound } from "next/navigation";
import Link from "next/link";
import {
  getAdjacentGroupIds,
  getConfirmedCandidate,
  getGroupDetail,
  getGroupPhotos,
  getKnownLocationNames,
} from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";
import { formatCamera, formatExposure, hasValidGps } from "@/lib/formatExif";
import { setBestShotOverrideAction } from "@/lib/actions/setBestShotOverride";
import { reopenForReviewAction } from "@/lib/actions/reviewSpecies";
import {
  deleteGroupAction,
  deletePhotoAction,
  mergeGroupsAction,
  removePhotoFromGroupAction,
} from "@/lib/actions/manageGroups";
import { wikipediaSearchUrl } from "@/lib/wikipedia";
import { SubmitButton } from "@/components/SubmitButton";
import { SetLocationForm } from "@/components/SetLocationForm";
import { ShareButton } from "@/components/ShareButton";
import { ConfirmButton } from "./ConfirmButton";

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
  const [mediumUrl, filmstrip, confirmedCandidate, adjacent, knownLocations] = await Promise.all([
    getSignedImageUrl(group.mediumKey),
    Promise.all(
      photos.map(async (photo) => ({
        ...photo,
        thumbUrl: await getSignedImageUrl(photo.thumbKey),
      })),
    ),
    getConfirmedCandidate(id),
    getAdjacentGroupIds(id, group.takenAt),
    getKnownLocationNames(),
  ]);

  const [prevGroupPhotoCount, nextGroupPhotoCount, prevThumbUrl, nextThumbUrl] =
    await Promise.all([
      adjacent.prevGroupId ? getGroupPhotos(adjacent.prevGroupId).then((p) => p.length) : 0,
      adjacent.nextGroupId ? getGroupPhotos(adjacent.nextGroupId).then((p) => p.length) : 0,
      adjacent.prevThumbKey ? getSignedImageUrl(adjacent.prevThumbKey) : null,
      adjacent.nextThumbKey ? getSignedImageUrl(adjacent.nextThumbKey) : null,
    ]);

  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-10 dark:bg-black">
      <div className="flex items-center justify-between">
        <Link href="/gallery" className="text-sm text-zinc-500 hover:underline">
          &larr; Back to gallery
        </Link>
        <div className="flex items-center gap-4">
          <ShareButton type="group" targetId={id} />
          <form action={deleteGroupAction.bind(null, id)}>
            <ConfirmButton
              label="Delete this group"
              confirmLabel="Confirm delete"
              pendingLabel="Deleting…"
              className="text-sm text-red-600 hover:underline dark:text-red-400"
              confirmClassName="text-sm text-red-600 hover:underline dark:text-red-400"
            />
          </form>
        </div>
      </div>

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
                // A plain <a>, not <Link>: Next's client-side transition
                // (pushState) never triggers the browser's :target match
                // that /review's highlight relies on (see that page's
                // comment) — only a real navigation does, which this
                // forces.
                <a
                  href={`/review#${id}`}
                  className="text-blue-600 hover:underline dark:text-blue-400"
                >
                  Not yet reviewed
                </a>
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
              {hasValidGps(group.gpsLat, group.gpsLng) ? (
                `${group.gpsLat!.toFixed(5)}, ${group.gpsLng!.toFixed(5)}`
              ) : (
                <>
                  <span>{group.locationName ?? "—"}</span>
                  <SetLocationForm groupId={id} knownLocations={knownLocations} />
                </>
              )}
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
                <div key={photo.photoId} className="flex flex-col items-center gap-1">
                  <form action={setBestShotOverrideAction.bind(null, id, photo.photoId)}>
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
                  <div className="flex gap-2 text-xs">
                    <form action={removePhotoFromGroupAction.bind(null, id, photo.photoId)}>
                      <SubmitButton
                        pendingLabel="…"
                        className="text-zinc-500 hover:underline"
                      >
                        Remove
                      </SubmitButton>
                    </form>
                    <form action={deletePhotoAction.bind(null, photo.photoId)}>
                      <ConfirmButton
                        label="Delete"
                        confirmLabel="Confirm?"
                        pendingLabel="…"
                        className="text-red-600 hover:underline dark:text-red-400"
                        confirmClassName="text-red-600 hover:underline dark:text-red-400"
                      />
                    </form>
                  </div>
                </div>
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
          <div className="flex flex-wrap gap-4">
            {adjacent.prevGroupId !== null && (
              <div className="flex items-center gap-3 rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
                {prevThumbUrl && (
                  // eslint-disable-next-line @next/next/no-img-element -- presigned R2 URL
                  <img
                    src={prevThumbUrl}
                    alt=""
                    className="h-16 w-16 rounded object-cover"
                  />
                )}
                <div className="flex flex-col items-start gap-1">
                  <span className="text-xs text-zinc-500">
                    Previous group ({prevGroupPhotoCount} photo
                    {prevGroupPhotoCount === 1 ? "" : "s"})
                  </span>
                  <form action={mergeGroupsAction.bind(null, id, adjacent.prevGroupId)}>
                    <SubmitButton
                      pendingLabel="Merging…"
                      className="rounded-md bg-zinc-200 px-3 py-1.5 text-sm text-black hover:bg-zinc-300 disabled:opacity-50 dark:bg-zinc-800 dark:text-zinc-50 dark:hover:bg-zinc-700"
                    >
                      Merge with this
                    </SubmitButton>
                  </form>
                </div>
              </div>
            )}
            {adjacent.nextGroupId !== null && (
              <div className="flex items-center gap-3 rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
                {nextThumbUrl && (
                  // eslint-disable-next-line @next/next/no-img-element -- presigned R2 URL
                  <img
                    src={nextThumbUrl}
                    alt=""
                    className="h-16 w-16 rounded object-cover"
                  />
                )}
                <div className="flex flex-col items-start gap-1">
                  <span className="text-xs text-zinc-500">
                    Next group ({nextGroupPhotoCount} photo
                    {nextGroupPhotoCount === 1 ? "" : "s"})
                  </span>
                  <form action={mergeGroupsAction.bind(null, id, adjacent.nextGroupId)}>
                    <SubmitButton
                      pendingLabel="Merging…"
                      className="rounded-md bg-zinc-200 px-3 py-1.5 text-sm text-black hover:bg-zinc-300 disabled:opacity-50 dark:bg-zinc-800 dark:text-zinc-50 dark:hover:bg-zinc-700"
                    >
                      Merge with this
                    </SubmitButton>
                  </form>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
