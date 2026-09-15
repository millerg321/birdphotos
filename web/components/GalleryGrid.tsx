"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getGroupMediumImageUrlAction } from "@/lib/actions/gallery";

export interface GalleryCardData {
  groupId: string;
  thumbUrl: string;
  speciesLabel: string;
  photoCount: number;
  isMissingLocation: boolean;
}

// Pure and exported for direct unit testing (see GalleryGrid.test.ts) —
// no wraparound, clamped to [0, length - 1]. Kept inside this "use
// client" file rather than split into its own plain module the way
// buildFilterUrl was (lib/galleryFilters.ts): that split exists only
// because a Server Component needed to call buildFilterUrl directly,
// which Next's RSC boundary forbids from a client module. Nothing
// server-side needs this one — only GalleryGrid itself, client-side —
// and Vitest doesn't enforce that RSC rule, so a plain test file can
// import it straight from here.
export function clampIndex(current: number, delta: number, length: number): number {
  if (length === 0) {
    return current;
  }
  return Math.min(Math.max(current + delta, 0), length - 1);
}

export function GalleryGrid({
  cards,
  isOwner,
}: {
  cards: GalleryCardData[];
  isOwner: boolean;
}) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  // Keyed by index rather than reset-then-set, so this never needs a
  // synchronous setState at the top of the effect below (React's
  // set-state-in-effect lint rule flags that as a cascading-render
  // risk) — staleness is a derived check (mediumResult below) instead
  // of a separate piece of reset state.
  const [mediumResult, setMediumResult] = useState<{ index: number; url: string | null } | null>(
    null,
  );

  // Re-fetches on every index change — the medium image is deliberately
  // never prefetched for the whole grid (see plan: gallery lightbox,
  // getGroupMediumImageUrlAction's own comment) — so each open/Prev/Next
  // shows the already-known thumbnail immediately, then swaps once the
  // larger image resolves.
  useEffect(() => {
    if (openIndex === null) {
      return;
    }
    let cancelled = false;
    getGroupMediumImageUrlAction(cards[openIndex].groupId).then((url) => {
      if (!cancelled) {
        setMediumResult({ index: openIndex, url });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [openIndex, cards]);

  const mediumUrl = mediumResult?.index === openIndex ? mediumResult.url : null;

  useEffect(() => {
    if (openIndex === null) {
      return;
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpenIndex(null);
      } else if (e.key === "ArrowLeft") {
        setOpenIndex((i) => (i === null ? i : clampIndex(i, -1, cards.length)));
      } else if (e.key === "ArrowRight") {
        setOpenIndex((i) => (i === null ? i : clampIndex(i, 1, cards.length)));
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [openIndex, cards.length]);

  return (
    <>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        {cards.map((card, index) => (
          <button
            key={card.groupId}
            type="button"
            onClick={() => setOpenIndex(index)}
            className="group relative overflow-hidden rounded-lg bg-zinc-100 text-left dark:bg-zinc-900"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- presigned R2 URLs, not a static/known-domain source Next/Image can optimize */}
            <img
              src={card.thumbUrl}
              alt=""
              className="aspect-square w-full object-cover transition-opacity group-hover:opacity-80"
            />

            {card.photoCount > 1 && (
              <span className="absolute top-1.5 right-1.5 rounded-full bg-black/70 px-1.5 py-0.5 text-xs font-medium text-white">
                ×{card.photoCount}
              </span>
            )}

            {isOwner && card.isMissingLocation && (
              <span className="absolute top-1.5 left-1.5 rounded-full bg-amber-600/90 px-1.5 py-0.5 text-xs font-medium text-white">
                No location
              </span>
            )}

            <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/80 to-transparent px-2 py-1.5 text-xs text-white">
              {card.speciesLabel}
            </span>
          </button>
        ))}
      </div>

      {openIndex !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4"
          onClick={() => setOpenIndex(null)}
        >
          <button
            type="button"
            onClick={() => setOpenIndex(null)}
            aria-label="Close"
            className="absolute top-4 right-4 text-2xl text-white/80 hover:text-white"
          >
            ×
          </button>

          <button
            type="button"
            disabled={openIndex === 0}
            onClick={(e) => {
              e.stopPropagation();
              setOpenIndex((i) => (i === null ? i : clampIndex(i, -1, cards.length)));
            }}
            aria-label="Previous"
            className="absolute left-4 text-3xl text-white/80 hover:text-white disabled:opacity-30"
          >
            ‹
          </button>
          <button
            type="button"
            disabled={openIndex === cards.length - 1}
            onClick={(e) => {
              e.stopPropagation();
              setOpenIndex((i) => (i === null ? i : clampIndex(i, 1, cards.length)));
            }}
            aria-label="Next"
            className="absolute right-4 text-3xl text-white/80 hover:text-white disabled:opacity-30"
          >
            ›
          </button>

          <div
            className="flex max-h-full w-full max-w-4xl flex-col items-center gap-3"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Fixed-size box, not just a max-* bound on the <img> itself:
                the thumbnail's native pixel size is small, so without a
                stable box around it the image rendered at that small
                native size, then visibly jumped to fill the screen once
                the much-bigger medium image loaded and replaced it. Both
                images now render into the same box via object-contain, so
                only their sharpness changes when the swap happens, not
                their apparent size — the thumbnail gets a blur while it's
                standing in, which clears once the real image is ready. */}
            <div className="flex h-[70vh] w-full items-center justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element -- presigned R2 URL */}
              <img
                src={mediumUrl ?? cards[openIndex].thumbUrl}
                alt=""
                className={`max-h-full max-w-full rounded-lg object-contain transition-[filter] duration-200 ${
                  mediumUrl ? "" : "blur-sm"
                }`}
              />
            </div>
            <div className="flex items-center gap-4 text-sm text-white">
              <span>{cards[openIndex].speciesLabel}</span>
              <Link
                href={`/groups/${cards[openIndex].groupId}`}
                className="text-blue-400 hover:underline"
              >
                View full details
              </Link>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
