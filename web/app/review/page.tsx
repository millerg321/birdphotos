import { getGroupCandidates, getReviewQueueGroups } from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";
import { confirmCandidateAction, rejectAllCandidatesAction } from "@/lib/actions/reviewSpecies";
import { wikipediaSearchUrl } from "@/lib/wikipedia";

// Same reasoning as app/gallery/page.tsx: DB queries and presigned URLs
// aren't visible to Next's static/dynamic heuristics, and this page
// must reflect the queue as it's worked through.
export const dynamic = "force-dynamic";

function formatCandidateLabel(commonName: string | null, rawLabel: string | null): string {
  return commonName ?? rawLabel ?? "Unknown";
}

export default async function ReviewPage() {
  const groups = await getReviewQueueGroups();

  const items = await Promise.all(
    groups.map(async (group) => {
      const [thumbUrl, candidates] = await Promise.all([
        getSignedImageUrl(group.thumbKey),
        getGroupCandidates(group.groupId),
      ]);
      return { ...group, thumbUrl, candidates };
    }),
  );

  return (
    <main className="min-h-screen bg-zinc-50 px-6 py-10 dark:bg-black">
      <h1 className="mb-6 text-2xl font-semibold text-black dark:text-zinc-50">
        Review ({items.length})
      </h1>

      {items.length === 0 && (
        <p className="text-zinc-500">Nothing waiting for review.</p>
      )}

      <div className="space-y-6">
        {items.map((item) => (
          <div
            key={item.groupId}
            className="flex flex-col gap-4 rounded-lg bg-zinc-100 p-4 sm:flex-row dark:bg-zinc-900"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- presigned R2 URL */}
            <img
              src={item.thumbUrl}
              alt=""
              className="h-40 w-40 flex-shrink-0 rounded-md object-cover"
            />

            <div className="flex-1 space-y-2">
              {item.candidates
                .filter((c) => c.status === "pending_review")
                .map((candidate) => (
                  <form
                    key={candidate.candidateId}
                    action={confirmCandidateAction.bind(
                      null,
                      item.groupId,
                      candidate.candidateId,
                    )}
                    className="flex items-center justify-between gap-3 rounded-md bg-white px-3 py-2 text-sm dark:bg-black"
                  >
                    <span className="text-black dark:text-zinc-50">
                      {formatCandidateLabel(candidate.commonName, candidate.rawLabel)}
                      {candidate.scientificName && (
                        <span className="text-zinc-500 italic"> — {candidate.scientificName}</span>
                      )}{" "}
                      <a
                        href={wikipediaSearchUrl(
                          candidate.scientificName ??
                            formatCandidateLabel(candidate.commonName, candidate.rawLabel),
                        )}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                      >
                        Wikipedia ↗
                      </a>
                    </span>
                    <span className="flex items-center gap-3">
                      <span className="text-zinc-500">
                        {candidate.confidence !== null
                          ? `${Math.round(candidate.confidence * 100)}%`
                          : "—"}
                      </span>
                      <button
                        type="submit"
                        className="rounded-full bg-black px-3 py-1 text-xs font-medium text-white dark:bg-white dark:text-black"
                      >
                        Confirm
                      </button>
                    </span>
                  </form>
                ))}

              <form action={rejectAllCandidatesAction.bind(null, item.groupId)}>
                <button
                  type="submit"
                  className="text-sm text-zinc-500 hover:underline"
                >
                  None of these / unidentified
                </button>
              </form>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
