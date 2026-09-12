"use client";

import { useFormStatus } from "react-dom";
import type { ReactNode } from "react";

// Disables itself while its enclosing <form>'s action is in flight —
// plain server-action forms give no feedback otherwise, and a fast
// double-click sends two requests for the same mutation. Merge in
// particular used to 500 on the second one (see worker/app/jobs/
// group_bursts.py merge_groups, now also made idempotent as a second
// layer of defense against the same race).
export function SubmitButton({
  children,
  pendingLabel,
  className,
}: {
  children: ReactNode;
  pendingLabel: string;
  className: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending} className={className}>
      {pending ? pendingLabel : children}
    </button>
  );
}
