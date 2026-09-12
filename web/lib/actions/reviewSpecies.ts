"use server";

import { revalidatePath } from "next/cache";
import {
  confirmCandidate as confirmCandidateQuery,
  rejectAllCandidates as rejectAllCandidatesQuery,
} from "@/lib/db/queries";
import { auth } from "@/lib/auth";

async function currentReviewerEmail(): Promise<string> {
  const session = await auth();
  const email = session?.user?.email;
  if (!email) {
    throw new Error("Not authenticated");
  }
  return email;
}

export async function confirmCandidateAction(
  groupId: string,
  candidateId: string,
): Promise<void> {
  const reviewedBy = await currentReviewerEmail();
  await confirmCandidateQuery(groupId, candidateId, reviewedBy);
  revalidatePath("/review");
  revalidatePath("/gallery");
  revalidatePath(`/groups/${groupId}`);
}

export async function rejectAllCandidatesAction(groupId: string): Promise<void> {
  const reviewedBy = await currentReviewerEmail();
  await rejectAllCandidatesQuery(groupId, reviewedBy);
  revalidatePath("/review");
}
