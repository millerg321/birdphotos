"use server";

import { revalidatePath } from "next/cache";
import { auth } from "@/lib/auth";

async function requireSession(): Promise<void> {
  const session = await auth();
  if (!session?.user?.email) {
    throw new Error("Not authenticated");
  }
}

// The group the action is invoked from always survives as intoGroupId —
// fromGroupId's photos (and species/tags) move into it and its own row
// is deleted (see worker/app/jobs/group_bursts.py merge_groups). Keeping
// the current page's group as the survivor means no redirect is needed
// after a merge.
export async function mergeGroupsAction(intoGroupId: string, fromGroupId: string): Promise<void> {
  await requireSession();

  const response = await fetch(`${process.env.WORKER_BASE_URL}/jobs/merge-groups`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Token": process.env.INTERNAL_API_TOKEN!,
    },
    body: JSON.stringify({ into_group_id: intoGroupId, from_group_id: fromGroupId }),
  });

  if (!response.ok) {
    throw new Error(`Worker merge failed: ${response.status} ${await response.text()}`);
  }

  revalidatePath(`/groups/${intoGroupId}`);
  revalidatePath("/gallery");
}
