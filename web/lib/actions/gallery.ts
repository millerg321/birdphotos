"use server";

import { getGroupMediumKey } from "@/lib/db/queries";
import { getSignedImageUrl } from "@/lib/storage";

// Deliberately public, unlike every other file in lib/actions/ (all
// gated by requireSession()) — this backs the gallery lightbox
// (components/GalleryGrid.tsx), and /gallery itself is public (see
// plan: ephemeral photo identification). An anonymous visitor already
// sees this exact photo's thumbnail on the public gallery grid; a
// slightly larger version of the same already-visible photo isn't a
// different exposure level.
export async function getGroupMediumImageUrlAction(groupId: string): Promise<string | null> {
  const mediumKey = await getGroupMediumKey(groupId);
  if (mediumKey === null) {
    return null;
  }
  return getSignedImageUrl(mediumKey);
}
