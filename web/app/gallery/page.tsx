import Link from "next/link";
import { getGalleryGroups } from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";

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
      <h1 className="mb-6 text-2xl font-semibold text-black dark:text-zinc-50">
        Gallery
      </h1>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        {cards.map((card) => (
          <Link
            key={card.groupId}
            href={`/groups/${card.groupId}`}
            className="group overflow-hidden rounded-lg bg-zinc-100 dark:bg-zinc-900"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- presigned R2 URLs, not a static/known-domain source Next/Image can optimize */}
            <img
              src={card.thumbUrl}
              alt=""
              className="aspect-square w-full object-cover transition-opacity group-hover:opacity-80"
            />
          </Link>
        ))}
      </div>
      {cards.length === 0 && (
        <p className="text-zinc-500">No photos yet.</p>
      )}
    </main>
  );
}
