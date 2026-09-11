import { notFound } from "next/navigation";
import Link from "next/link";
import { getGroupDetail } from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";
import { formatCamera, formatExposure } from "@/lib/formatExif";

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

  const mediumUrl = await getSignedImageUrl(group.mediumKey);

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
    </main>
  );
}
