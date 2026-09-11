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
