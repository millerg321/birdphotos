"use client";

import { useState } from "react";
import { reclassifyGroupAction } from "@/lib/actions/manageGroups";

// A client component (not a plain <form action={...}>) so a transient
// failure calling the escalation model shows an inline message instead
// of crashing the whole review queue to Next.js's default error page —
// same reasoning as app/groups/[id]/SetLocationForm.tsx.
export function ReclassifyButton({ groupId }: { groupId: string }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setPending(true);
    setError(null);
    try {
      await reclassifyGroupAction(groupId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reclassification failed");
    }
    setPending(false);
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={pending}
        className="text-sm text-zinc-500 hover:underline disabled:opacity-50"
      >
        {pending ? "Trying a better model…" : "Try a better model"}
      </button>
      {error && <span className="text-xs text-red-600 dark:text-red-400">{error}</span>}
    </span>
  );
}
