"use client";

import { useState, type FormEvent } from "react";
import { setGroupLocationAction } from "@/lib/actions/manageGroups";
import { LocationAutocomplete } from "@/components/LocationAutocomplete";

// A client component (not a plain <form action={...}>) so a bad place
// name — Nominatim finding nothing — can show an inline error instead
// of crashing to Next.js's default error page (see
// worker/app/locations.py set_group_location, which raises ValueError
// in that case).
export function SetLocationForm({
  groupId,
  knownLocations,
}: {
  groupId: string;
  knownLocations: string[];
}) {
  const [placeName, setPlaceName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(name: string) {
    setSubmitting(true);
    setError(null);
    try {
      await setGroupLocationAction(groupId, name);
      setPlaceName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not set location");
    }
    setSubmitting(false);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = placeName.trim();
    if (!trimmed) {
      return;
    }
    await submit(trimmed);
  }

  return (
    <form onSubmit={handleSubmit} className="mt-1 flex flex-wrap items-center gap-2">
      <LocationAutocomplete
        value={placeName}
        onValueChange={setPlaceName}
        // Saves immediately on selection — one less click, and the name
        // is already known-good (it geocoded successfully before).
        onSelect={submit}
        options={knownLocations}
        placeholder="e.g. London, UK"
        disabled={submitting}
        className="rounded-md border border-zinc-300 bg-transparent px-2 py-1 text-xs text-black placeholder:text-zinc-400 dark:border-zinc-700 dark:text-zinc-50"
      />
      <button
        type="submit"
        disabled={submitting || placeName.trim() === ""}
        className="rounded-md bg-zinc-200 px-2 py-1 text-xs text-black hover:bg-zinc-300 disabled:opacity-50 dark:bg-zinc-800 dark:text-zinc-50 dark:hover:bg-zinc-700"
      >
        {submitting ? "Setting…" : "Set"}
      </button>
      {error && <span className="text-xs text-red-600 dark:text-red-400">{error}</span>}
    </form>
  );
}
