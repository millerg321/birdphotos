"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { auth } from "@/lib/auth";

async function requireSession(): Promise<void> {
  const session = await auth();
  if (!session?.user?.email) {
    throw new Error("Not authenticated");
  }
}

async function callWorker(path: string, body: Record<string, string>): Promise<unknown> {
  const response = await fetch(`${process.env.WORKER_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Token": process.env.INTERNAL_API_TOKEN!,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`Worker request to ${path} failed: ${response.status} ${await response.text()}`);
  }

  return response.json();
}

// The group the action is invoked from always survives as intoGroupId —
// fromGroupId's photos (and species/tags) move into it and its own row
// is deleted (see worker/app/jobs/group_bursts.py merge_groups). Keeping
// the current page's group as the survivor means no redirect is needed
// after a merge.
export async function mergeGroupsAction(intoGroupId: string, fromGroupId: string): Promise<void> {
  await requireSession();
  await callWorker("/jobs/merge-groups", { into_group_id: intoGroupId, from_group_id: fromGroupId });
  revalidatePath(`/groups/${intoGroupId}`);
  revalidatePath("/gallery");
}

// The undo for an accidental mergeGroupsAction: pulls one photo back out
// into its own new group (see worker/app/jobs/group_bursts.py
// remove_photo_from_group). The current page's group still exists
// afterward (it just has one fewer photo), so no redirect is needed.
export async function removePhotoFromGroupAction(
  groupId: string,
  photoId: string,
): Promise<void> {
  await requireSession();
  await callWorker("/jobs/remove-photo-from-group", { photo_id: photoId });
  revalidatePath(`/groups/${groupId}`);
  revalidatePath("/gallery");
}

// Permanently deletes one photo. If it was the group's last photo, the
// group goes with it — redirect to the gallery rather than refresh a
// page that would now 404.
export async function deletePhotoAction(photoId: string): Promise<void> {
  await requireSession();
  const result = (await callWorker("/jobs/delete-photo", { photo_id: photoId })) as {
    surviving_group_id: string | null;
  };
  revalidatePath("/gallery");
  if (result.surviving_group_id === null) {
    redirect("/gallery");
  }
  revalidatePath(`/groups/${result.surviving_group_id}`);
}

// Permanently deletes an entire group and all its photos — always
// redirects to the gallery, since the current page's group is gone.
export async function deleteGroupAction(groupId: string): Promise<void> {
  await requireSession();
  await callWorker("/jobs/delete-group", { group_id: groupId });
  revalidatePath("/gallery");
  redirect("/gallery");
}
