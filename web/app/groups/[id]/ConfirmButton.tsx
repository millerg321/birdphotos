"use client";

import { useState } from "react";
import { useFormStatus } from "react-dom";

// Two-click confirm for destructive actions (delete photo/group) —
// avoids a blocking native confirm() dialog in favor of an inline
// "Confirm? / Cancel" swap. Must be a client component since it needs
// local state to gate the actual submit button's render.
export function ConfirmButton({
  label,
  confirmLabel,
  pendingLabel,
  className,
  confirmClassName,
}: {
  label: string;
  confirmLabel: string;
  pendingLabel: string;
  className: string;
  confirmClassName: string;
}) {
  const [confirming, setConfirming] = useState(false);
  const { pending } = useFormStatus();

  if (!confirming) {
    return (
      <button type="button" onClick={() => setConfirming(true)} className={className}>
        {label}
      </button>
    );
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button type="submit" disabled={pending} className={confirmClassName}>
        {pending ? pendingLabel : confirmLabel}
      </button>
      <button
        type="button"
        onClick={() => setConfirming(false)}
        className="text-xs text-zinc-500 hover:underline"
      >
        Cancel
      </button>
    </span>
  );
}
