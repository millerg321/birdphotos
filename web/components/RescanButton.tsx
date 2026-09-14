"use client";

import { useState } from "react";
import { rescanAction } from "@/lib/actions/upload";

// A client component (not a plain <form action={...}>) so a failure
// calling the worker shows an inline message instead of crashing to
// Next.js's default error page — same reasoning as
// components/SetLocationForm.tsx. Shared between app/upload (after a
// batch upload) and app/review (so a stuck/unclassified group doesn't
// require a trip back to /upload to retry — see rescanAction's own
// docstring: this is a full-library rescan, not scoped to one group).
export function RescanButton() {
  const [rescanning, setRescanning] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  async function handleClick() {
    setRescanning(true);
    setResult(null);
    try {
      const r = await rescanAction();
      setResult(
        `Scored ${r.scored}, ${r.groups} burst group(s) total, ${r.classified} newly classified`,
      );
    } catch (err) {
      setResult(err instanceof Error ? err.message : "Rescan failed");
    }
    setRescanning(false);
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={rescanning}
        className="rounded-md bg-zinc-200 px-3 py-1.5 text-sm text-black hover:bg-zinc-300 disabled:opacity-50 dark:bg-zinc-800 dark:text-zinc-50 dark:hover:bg-zinc-700"
      >
        {rescanning ? "Scoring, grouping & classifying…" : "Score, group & classify new photos"}
      </button>
      {result && <span className="text-sm text-zinc-700 dark:text-zinc-300">{result}</span>}
    </span>
  );
}
