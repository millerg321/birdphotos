"use server";

import { auth } from "@/lib/auth";
import { getOrCreateShareLink } from "@/lib/db/queries";

// Not shared with manageGroups.ts's own requireSession — this codebase
// already duplicates this small helper per action file rather than
// factoring out a shared one (see reviewSpecies.ts's currentReviewerEmail
// for the same pattern).
async function requireSession(): Promise<void> {
  const session = await auth();
  if (!session?.user?.email) {
    throw new Error("Not authenticated");
  }
}

// Only the owner can mint a share link (even though the resulting link
// itself is public) — see plan: Phase 6 — sharing. Returns the token
// directly rather than revalidatePath-ing: nothing on the calling page's
// own rendered data changes, the caller (ShareButton) just needs it back
// to display inline, same shape as setGroupLocationAction.
export async function createShareLinkAction(
  type: "group" | "species",
  targetId: string,
): Promise<{ token: string }> {
  await requireSession();
  const token = await getOrCreateShareLink(type, targetId);
  return { token };
}
