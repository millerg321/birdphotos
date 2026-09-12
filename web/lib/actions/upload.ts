"use server";

import { randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { getSignedUploadUrl } from "@/lib/storage";
import { auth } from "@/lib/auth";

async function requireSession(): Promise<void> {
  const session = await auth();
  if (!session?.user?.email) {
    throw new Error("Not authenticated");
  }
}

export interface StagedUpload {
  r2Key: string;
  uploadUrl: string;
}

// One staging key per file, under its own prefix so a crashed/abandoned
// upload never gets mixed up with real imported photos. The worker
// deletes the object once it's successfully processed (see
// worker/app/jobs/import_upload.py) — nothing here is meant to be
// long-lived.
export async function getUploadUrlAction(filename: string): Promise<StagedUpload> {
  await requireSession();
  const extension = filename.includes(".") ? filename.split(".").pop() : "jpg";
  const r2Key = `uploads/${randomUUID()}.${extension}`;
  const uploadUrl = await getSignedUploadUrl(r2Key, "application/octet-stream");
  return { r2Key, uploadUrl };
}

export interface ProcessUploadsResult {
  imported: number;
  errors: { r2Key: string; error: string }[];
}

export async function processUploadsAction(r2Keys: string[]): Promise<ProcessUploadsResult> {
  await requireSession();
  if (r2Keys.length === 0) {
    return { imported: 0, errors: [] };
  }

  const response = await fetch(`${process.env.WORKER_BASE_URL}/import/from-upload`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Token": process.env.INTERNAL_API_TOKEN!,
    },
    body: JSON.stringify({ r2_keys: r2Keys }),
  });

  if (!response.ok) {
    throw new Error(`Worker import failed: ${response.status} ${await response.text()}`);
  }

  const results: { r2_key: string; photo_id: string | null; error: string | null }[] =
    await response.json();

  revalidatePath("/gallery");

  return {
    imported: results.filter((r) => r.photo_id !== null).length,
    errors: results
      .filter((r) => r.error !== null)
      .map((r) => ({ r2Key: r.r2_key, error: r.error! })),
  };
}

export interface RescanResult {
  scored: number;
  groups: number;
}

// Manual trigger only (see plan: manual upload) — scoring/grouping is a
// full-library rescan, not incremental, so it deliberately doesn't run
// automatically after every upload. Hit this once after uploading a
// batch. May go away if/once uploads get proper incremental grouping.
export async function rescanAction(): Promise<RescanResult> {
  await requireSession();

  const response = await fetch(`${process.env.WORKER_BASE_URL}/jobs/backfill-and-group`, {
    method: "POST",
    headers: { "X-Internal-Token": process.env.INTERNAL_API_TOKEN! },
  });

  if (!response.ok) {
    throw new Error(`Worker rescan failed: ${response.status} ${await response.text()}`);
  }

  const result: RescanResult = await response.json();
  revalidatePath("/gallery");
  return result;
}
