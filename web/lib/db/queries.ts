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

export async function getReviewQueueGroups() {
  return db
    .selectFrom("burst_groups as bg")
    .innerJoin("photos as p", (join) => join.on((_eb) => EFFECTIVE_BEST_SHOT))
    .where((eb) =>
      eb.exists(
        eb
          .selectFrom("burst_group_species as bgs")
          .select("bgs.id")
          .whereRef("bgs.burst_group_id", "=", "bg.id")
          .where("bgs.status", "=", "pending_review"),
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
