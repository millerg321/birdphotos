import { randomUUID } from "node:crypto";
import { sql } from "kysely";
import { db } from "./client";

// Matches worker/app/queries.py effective_best_shot_photo_id: an explicit
// override always wins over the computed best shot (see plan: Data Model).
const EFFECTIVE_BEST_SHOT = sql<boolean>`coalesce(bg.best_shot_override_photo_id, bg.best_shot_photo_id) = p.id`;

export async function getGalleryGroups() {
  return db
    .selectFrom("burst_groups as bg")
    .innerJoin("photos as p", (join) => join.on((_eb) => EFFECTIVE_BEST_SHOT))
    .select([
      "bg.id as groupId",
      "p.id as photoId",
      "p.r2_key_thumb as thumbKey",
      "p.taken_at as takenAt",
      "p.camera_model as cameraModel",
    ])
    .orderBy("p.taken_at", "desc")
    .execute();
}

export async function getGroupDetail(groupId: string) {
  const group = await db
    .selectFrom("burst_groups as bg")
    .innerJoin("photos as p", (join) => join.on((_eb) => EFFECTIVE_BEST_SHOT))
    .select([
      "bg.id as groupId",
      "bg.best_shot_override_photo_id as overridePhotoId",
      "p.id as photoId",
      "p.r2_key_medium as mediumKey",
      "p.taken_at as takenAt",
      "p.camera_make as cameraMake",
      "p.camera_model as cameraModel",
      "p.focal_length_mm as focalLengthMm",
      "p.aperture",
      "p.iso",
      "p.shutter_speed as shutterSpeed",
      "p.gps_lat as gpsLat",
      "p.gps_lng as gpsLng",
      "p.width",
      "p.height",
    ])
    .where("bg.id", "=", groupId)
    .executeTakeFirst();

  return group ?? null;
}

export async function getGroupPhotos(groupId: string) {
  return db
    .selectFrom("photos as p")
    .select([
      "p.id as photoId",
      "p.r2_key_thumb as thumbKey",
      "p.taken_at as takenAt",
      "p.sharpness_score as sharpnessScore",
      "p.exposure_score as exposureScore",
    ])
    .where("p.burst_group_id", "=", groupId)
    .orderBy("p.taken_at", "asc")
    .execute();
}

export async function setBestShotOverride(groupId: string, photoId: string | null) {
  await db
    .updateTable("burst_groups")
    .set({ best_shot_override_photo_id: photoId })
    .where("id", "=", groupId)
    .execute();
}

// A group needs attention as long as nothing's confirmed — this covers
// both "still has pending_review candidates" and "marked unidentified"
// (all rejected, none confirmed). Previously only the first case showed
// here, so clicking "None of these" made a group vanish from the queue
// entirely with no way back except knowing its direct URL.
export async function getReviewQueueGroups() {
  return db
    .selectFrom("burst_groups as bg")
    .innerJoin("photos as p", (join) => join.on((_eb) => EFFECTIVE_BEST_SHOT))
    .where((eb) =>
      eb.not(
        eb.exists(
          eb
            .selectFrom("burst_group_species as bgs")
            .select("bgs.id")
            .whereRef("bgs.burst_group_id", "=", "bg.id")
            .where("bgs.status", "=", "confirmed"),
        ),
      ),
    )
    .select(["bg.id as groupId", "p.r2_key_thumb as thumbKey", "p.taken_at as takenAt"])
    .orderBy("p.taken_at", "desc")
    .execute();
}

export async function getGroupCandidates(groupId: string) {
  return db
    .selectFrom("burst_group_species as bgs")
    .leftJoin("species as s", "s.id", "bgs.species_id")
    .select([
      "bgs.id as candidateId",
      "bgs.raw_label as rawLabel",
      "bgs.confidence",
      "bgs.status",
      "s.common_name as commonName",
      "s.scientific_name as scientificName",
    ])
    .where("bgs.burst_group_id", "=", groupId)
    .orderBy("bgs.confidence", "desc")
    .execute();
}

export async function confirmCandidate(
  groupId: string,
  candidateId: string,
  reviewedBy: string,
) {
  await db.transaction().execute(async (trx) => {
    await trx
      .updateTable("burst_group_species")
      .set({ status: "rejected" })
      .where("burst_group_id", "=", groupId)
      .where("id", "!=", candidateId)
      .execute();

    await trx
      .updateTable("burst_group_species")
      .set({ status: "confirmed", reviewed_by: reviewedBy, reviewed_at: new Date() })
      .where("id", "=", candidateId)
      .execute();
  });
}

export async function rejectAllCandidates(groupId: string, reviewedBy: string) {
  await db
    .updateTable("burst_group_species")
    .set({ status: "rejected", reviewed_by: reviewedBy, reviewed_at: new Date() })
    .where("burst_group_id", "=", groupId)
    .execute();
}

export async function getConfirmedCandidate(groupId: string) {
  const row = await db
    .selectFrom("burst_group_species as bgs")
    .leftJoin("species as s", "s.id", "bgs.species_id")
    .select([
      "bgs.id as candidateId",
      "bgs.raw_label as rawLabel",
      "bgs.reviewed_by as reviewedBy",
      "bgs.reviewed_at as reviewedAt",
      "s.common_name as commonName",
      "s.scientific_name as scientificName",
    ])
    .where("bgs.burst_group_id", "=", groupId)
    .where("bgs.status", "=", "confirmed")
    .executeTakeFirst();

  return row ?? null;
}

export function slugify(text: string): string {
  const slug = text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "unknown";
}

function isUniqueViolation(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "code" in err &&
    (err as { code: unknown }).code === "23505"
  );
}

// Matches on common_name (case-insensitive, same as the Python worker's
// get_or_create_species) OR on the generated slug — the two aren't the
// same check: slug normalizes away punctuation/whitespace differences
// that an exact-modulo-case common_name match doesn't, so two typed
// names that *look* different but slugify identically (e.g. "Ring
// necked Parakeet" vs "Ring-necked Parakeet") used to pass the
// common_name check, then crash the whole request on the slug's unique
// constraint. Caught this exact crash in production. The catch below is
// a second line of defense for a same-slug race between two concurrent
// inserts, which the upfront check can't rule out.
async function getOrCreateSpeciesId(
  executor: typeof db,
  commonName: string,
): Promise<string> {
  const slug = slugify(commonName);

  const existing = await executor
    .selectFrom("species")
    .select("id")
    .where((eb) => eb.or([eb("common_name", "ilike", commonName), eb("slug", "=", slug)]))
    .executeTakeFirst();
  if (existing) return existing.id;

  try {
    // id has no DB-side default (the worker generates it app-side with
    // uuid.uuid4() too — see app/models.py uuid_pk()), so it's required here.
    const inserted = await executor
      .insertInto("species")
      .values({ id: randomUUID(), common_name: commonName, slug })
      .returning("id")
      .executeTakeFirstOrThrow();
    return inserted.id;
  } catch (err) {
    if (!isUniqueViolation(err)) {
      throw err;
    }
    const bySlug = await executor
      .selectFrom("species")
      .select("id")
      .where("slug", "=", slug)
      .executeTakeFirstOrThrow();
    return bySlug.id;
  }
}

// Lets a reviewer type the correct species directly when none of the AI
// candidates are right, rather than being stuck with only "confirm one
// of these three" or "mark unidentified with no way to say what it
// actually is".
export async function addManualSpecies(
  groupId: string,
  commonName: string,
  reviewedBy: string,
) {
  await db.transaction().execute(async (trx) => {
    const speciesId = await getOrCreateSpeciesId(trx, commonName);

    await trx
      .updateTable("burst_group_species")
      .set({ status: "rejected" })
      .where("burst_group_id", "=", groupId)
      .where("status", "=", "pending_review")
      .execute();

    await trx
      .insertInto("burst_group_species")
      .values({
        id: randomUUID(),
        burst_group_id: groupId,
        species_id: speciesId,
        raw_label: commonName,
        source: "manual",
        status: "confirmed",
        reviewed_by: reviewedBy,
        reviewed_at: new Date(),
      })
      .execute();
  });
}

// Puts every candidate for the group (confirmed and rejected alike) back
// to pending_review and clears the review attribution — the group then
// reappears in /review so a mis-click can be corrected, since there was
// previously no way to undo a confirmation once made.
export async function reopenGroupForReview(groupId: string) {
  await db
    .updateTable("burst_group_species")
    .set({ status: "pending_review", reviewed_by: null, reviewed_at: null })
    .where("burst_group_id", "=", groupId)
    .execute();
}
