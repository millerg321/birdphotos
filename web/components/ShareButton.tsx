"use client";

import { useState, useTransition } from "react";
import { createShareLinkAction } from "@/lib/actions/shareLinks";

// Generic over both share types (see plan: Phase 6 — sharing) — one
// component, one action, varying props, rather than a separate
// component per type.
export function ShareButton({
  type,
  targetId,
}: {
  type: "group" | "species";
  targetId: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [isPending, startTransition] = useTransition();

  // Calls the server action directly from onClick rather than via a
  // <form action={...}> — this needs the token back on the client to
  // display inline, not just a revalidate-on-submit (same reason
  // SetLocationForm calls its action directly instead of relying on
  // native form submission).
  function handleShare() {
    startTransition(async () => {
      const { token } = await createShareLinkAction(type, targetId);
      setUrl(`${window.location.origin}/s/${token}`);
    });
  }

  async function handleCopy() {
    if (!url) {
      return;
    }
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (url) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <input
          readOnly
          value={url}
          onFocus={(e) => e.target.select()}
          aria-label="Share link"
          className="w-56 rounded-md border border-zinc-300 bg-white px-2 py-1 text-black dark:border-zinc-700 dark:bg-black dark:text-zinc-50"
        />
        <button
          type="button"
          onClick={handleCopy}
          className="text-blue-600 hover:underline dark:text-blue-400"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={handleShare}
      disabled={isPending}
      className="text-sm text-blue-600 hover:underline dark:text-blue-400"
    >
      {isPending ? "Sharing…" : "Share"}
    </button>
  );
}
