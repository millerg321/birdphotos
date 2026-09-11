"use server";

import { revalidatePath } from "next/cache";
import { setBestShotOverride as setBestShotOverrideQuery } from "@/lib/db/queries";

export async function setBestShotOverrideAction(
  groupId: string,
  photoId: string | null,
): Promise<void> {
  await setBestShotOverrideQuery(groupId, photoId);
  revalidatePath(`/groups/${groupId}`);
  revalidatePath("/gallery");
}
