"use client";

import { useRouter } from "next/navigation";
import { buildFilterUrl, type GalleryFilters } from "@/lib/galleryFilters";

export interface SpeciesOption {
  slug: string;
  commonName: string;
}

export function GalleryFilterBar({
  species,
  locations,
  current,
}: {
  species: SpeciesOption[];
  locations: string[];
  current: GalleryFilters;
}) {
  const router = useRouter();
  const hasActiveFilter = !!(current.species || current.location || current.from || current.to);

  // Every control in this component changes what's shown, so every call
  // resets page back to 1 (see plan: gallery pagination) — otherwise
  // changing a filter while on, say, page 3 could land on an empty or
  // unrelated page 3 of the new result set. Done here once rather than
  // in each individual onChange below, so a future control can't forget
  // it.
  function update(updates: GalleryFilters) {
    router.push(buildFilterUrl(current, { ...updates, page: null }));
  }

  return (
    <div className="mb-6 flex flex-wrap items-center gap-2 text-sm">
      <select
        value={current.species ?? ""}
        onChange={(e) => update({ species: e.target.value || null })}
        aria-label="Filter by species"
        className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-black dark:border-zinc-700 dark:bg-black dark:text-zinc-50"
      >
        <option value="">All species</option>
        {species.map((s) => (
          <option key={s.slug} value={s.slug}>
            {s.commonName}
          </option>
        ))}
      </select>
      <select
        value={current.location ?? ""}
        onChange={(e) => update({ location: e.target.value || null })}
        aria-label="Filter by location"
        className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-black dark:border-zinc-700 dark:bg-black dark:text-zinc-50"
      >
        <option value="">All locations</option>
        {locations.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>
      <input
        type="date"
        value={current.from ?? ""}
        onChange={(e) => update({ from: e.target.value || null })}
        aria-label="From date"
        className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-black dark:border-zinc-700 dark:bg-black dark:text-zinc-50"
      />
      <span className="text-zinc-500">to</span>
      <input
        type="date"
        value={current.to ?? ""}
        onChange={(e) => update({ to: e.target.value || null })}
        aria-label="To date"
        className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-black dark:border-zinc-700 dark:bg-black dark:text-zinc-50"
      />
      <select
        value={current.sort ?? "newest"}
        onChange={(e) => update({ sort: e.target.value === "newest" ? null : e.target.value })}
        aria-label="Sort by"
        className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-black dark:border-zinc-700 dark:bg-black dark:text-zinc-50"
      >
        <option value="newest">Newest first</option>
        <option value="oldest">Oldest first</option>
        <option value="sharpest">Sharpest</option>
        <option value="most-photos">Most photos</option>
      </select>
      {hasActiveFilter && (
        <button
          type="button"
          onClick={() => update({ species: null, location: null, from: null, to: null })}
          className="text-zinc-500 hover:underline"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
