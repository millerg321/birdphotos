import { notFound } from "next/navigation";
import Link from "next/link";
import { getGroupDetail, getGroupPhotos } from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";
import { formatCamera, formatExposure } from "@/lib/formatExif";
import { setBestShotOverrideAction } from "@/lib/actions/setBestShotOverride";

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
  const [mediumUrl, filmstrip] = await Promise.all([
    getSignedImageUrl(group.mediumKey),
    Promise.all(
      photos.map(async (photo) => ({
        ...photo,
        thumbUrl: await getSignedImageUrl(photo.thumbKey),
      })),
    ),
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
    </main>
  );
}
