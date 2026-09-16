import { randomUUID } from "node:crypto";
import { sql } from "kysely";
import { db } from "./client";

// Matches worker/app/queries.py effective_best_shot_photo_id: an explicit
// override always wins over the computed best shot (see plan: Data Model).
const EFFECTIVE_BEST_SHOT = sql<boolean>`coalesce(bg.best_shot_override_photo_id, bg.best_shot_photo_id) = p.id`;

export interface GalleryGroupsFilter {
  unreviewed?: boolean;
  speciesSlug?: string;
  location?: string;
  from?: string;
  to?: string;
  sort?: "newest" | "oldest" | "sharpest" | "most-photos";
}

// See plan: gallery pagination — a round number, not tied to the grid's
// column counts at each breakpoint (grid-cols-2/3/4/5 in GalleryGrid.tsx);
// the last page not filling a full row is fine, same as the unpaginated
// gallery's last row never guaranteed one either.
export const GALLERY_PAGE_SIZE = 30;

// The joins + WHERE clauses shared by getGalleryGroups (a page of results)
// and getGalleryGroupsCount (how many total, to compute page count) — kept
// as one function so the two can never drift apart on what "matches this
// filter" means. Deliberately stops before .select()/.orderBy(): those
// differ between the two callers (columns needed vs. just a count; sort
// order is meaningless for a count).
//
// filter.unreviewed restricts to groups with no confirmed species — the
// exact same condition that makes a card show "Unreviewed" in the first
// place, so the toggle only ever hides cards already labeled that way,
// never something inconsistent with what's on screen. filter.speciesSlug/
// location/from/to are independent and combine with AND (and with
// unreviewed, though a group with a confirmed species obviously never
// matches both) — see plan: gallery filtering.
function galleryGroupsBaseQuery(filter: GalleryGroupsFilter) {
  let query = db
    .selectFrom("burst_groups as bg")
    .innerJoin("photos as p", (join) => join.on((_eb) => EFFECTIVE_BEST_SHOT))
    .leftJoin("locations as l", "l.id", "p.location_id")
    .leftJoin(
      (eb) =>
        eb
          .selectFrom("burst_group_species as bgs")
          .leftJoin("species as s", "s.id", "bgs.species_id")
          .select([
            "bgs.burst_group_id",
            "s.common_name as commonName",
            "s.slug as speciesSlug",
            "bgs.raw_label as rawLabel",
          ])
          .where("bgs.status", "=", "confirmed")
          // Defense in depth: the rest of the app assumes at most one
          // confirmed row per group, but a real bug once let two coexist
          // (see addManualSpecies) — DISTINCT ON keeps this join from
          // ever producing two rows for the same group (a React
          // duplicate-key crash on this page) even if that invariant is
          // ever violated again. Most-recently-reviewed wins.
          .distinctOn("bgs.burst_group_id")
          .orderBy("bgs.burst_group_id")
          .orderBy("bgs.reviewed_at", "desc")
          .as("confirmed"),
      (join) => join.onRef("confirmed.burst_group_id", "=", "bg.id"),
    );

  if (filter.unreviewed) {
    query = query.where("confirmed.burst_group_id", "is", null);
  }
  if (filter.speciesSlug) {
    query = query.where("confirmed.speciesSlug", "=", filter.speciesSlug);
  }
  if (filter.location) {
    query = query.where("l.name", "=", filter.location);
  }
  if (filter.from) {
    query = query.where("p.taken_at", ">=", new Date(filter.from));
  }
  if (filter.to) {
    // Inclusive of the whole "to" day, not just midnight at its start.
    const to = new Date(filter.to);
    to.setDate(to.getDate() + 1);
    query = query.where("p.taken_at", "<", to);
  }

  return query;
}

// Enriched for the gallery cards: confirmed species (null on both
// fields means unreviewed — same meaning as getConfirmedCandidate
// returning null, just bulk-fetched here instead of per-group), photo
// count (for the burst-count badge), and raw GPS/location fields (the
// page applies hasValidGps + locationName itself, same as the group
// detail page, rather than duplicating that decision here).
export async function getGalleryGroups(
  filter: GalleryGroupsFilter = {},
  page = 1,
  pageSize = GALLERY_PAGE_SIZE,
) {
  let query = galleryGroupsBaseQuery(filter).select((eb) => [
    "bg.id as groupId",
    "p.id as photoId",
    "p.r2_key_thumb as thumbKey",
    "p.taken_at as takenAt",
    "p.camera_model as cameraModel",
    "p.gps_lat as gpsLat",
    "p.gps_lng as gpsLng",
    "l.name as locationName",
    "confirmed.commonName as speciesCommonName",
    "confirmed.rawLabel as speciesRawLabel",
    eb
      .selectFrom("photos as p2")
      .select((eb2) => eb2.fn.countAll<number>().as("count"))
      .whereRef("p2.burst_group_id", "=", "bg.id")
      .as("photoCount"),
  ]);

  switch (filter.sort) {
    case "oldest":
      query = query.orderBy("p.taken_at", "asc");
      break;
    case "sharpest":
      // Raw sql, not Kysely's typed orderBy: not every photo has this
      // scored yet (only after backfill_scores has run), and Postgres
      // defaults DESC to NULLS FIRST, which would wrongly push every
      // unscored photo to the very top.
      query = query.orderBy(sql`p.sharpness_score desc nulls last`);
      break;
    case "most-photos":
      // photoCount is a subquery-computed select alias, not a table
      // column — ordering by it still needs a raw fragment rather than
      // Kysely's typed orderBy.
      query = query.orderBy(sql`"photoCount" desc`);
      break;
    default:
      query = query.orderBy("p.taken_at", "desc");
  }

  return query
    .limit(pageSize)
    .offset((page - 1) * pageSize)
    .execute();
}

// Total matching groups for `filter`, ignoring page/pageSize — used to
// compute how many pages there are (see plan: gallery pagination).
export async function getGalleryGroupsCount(filter: GalleryGroupsFilter = {}): Promise<number> {
  const row = await galleryGroupsBaseQuery(filter)
    .select((eb) => eb.fn.countAll<number>().as("count"))
    .executeTakeFirst();
  return row?.count ?? 0;
}

// Powers the gallery lightbox's lazy-loaded larger image (see plan:
// gallery lightbox) — cards only ever carry a signed thumbnail URL
// (getGalleryGroups), since presigning a medium URL for every card on
// every gallery load would be wasted work at any real library size;
// this looks up just the one key needed, on demand, when the lightbox
// actually opens for a given group. Does its own DB lookup via the
// same EFFECTIVE_BEST_SHOT join as everywhere else in this file,
// rather than trusting a client-supplied key.
export async function getGroupMediumKey(groupId: string): Promise<string | null> {
  const row = await db
    .selectFrom("burst_groups as bg")
    .innerJoin("photos as p", (join) => join.on((_eb) => EFFECTIVE_BEST_SHOT))
    .where("bg.id", "=", groupId)
    .select("p.r2_key_medium as mediumKey")
    .executeTakeFirst();
  return row?.mediumKey ?? null;
}

// Powers the species filter dropdown (see plan: gallery filtering) —
// only species with an actual matched Species row (i.e. bgs.species_id
// is set), same scope as everywhere else a "which species" identity is
// needed; a manually-tagged candidate with no match has no slug to
// filter by and just isn't offered as a filter option.
export async function getConfirmedSpeciesList() {
  return db
    .selectFrom("burst_group_species as bgs")
    .innerJoin("species as s", "s.id", "bgs.species_id")
    .where("bgs.status", "=", "confirmed")
    .select(["s.slug", "s.common_name as commonName"])
    .distinct()
    .orderBy("s.common_name")
    .execute();
}

// Powers location autocomplete (see plan: location autocomplete) — the
// `locations` table is small and barely changes (a personal library has
// a handful to a few dozen distinct places, already deduplicated by name
// via get_or_create_location, worker/app/locations.py), so this is
// fetched once per page load and filtered client-side as the user
// types, the same "small reference list, no per-keystroke network call"
// shape as getConfirmedSpeciesList above.
export async function getKnownLocationNames(): Promise<string[]> {
  const rows = await db.selectFrom("locations").select("name").orderBy("name").execute();
  return rows.map((r) => r.name);
}

// Powers the gallery's "Needs review (N)" toggle label regardless of
// which tab is currently active — same "no confirmed candidate"
// condition as getGalleryGroups's unreviewed filter and
// getReviewQueueGroups, kept as its own cheap count rather than
// requiring a second full getGalleryGroups({ unreviewed: true }) fetch
// just to read cards.length.
export async function getUnreviewedGalleryCount(): Promise<number> {
  const row = await db
    .selectFrom("burst_groups as bg")
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
    .select((eb) => eb.fn.countAll<number>().as("count"))
    .executeTakeFirst();

  return row?.count ?? 0;
}

export async function getGroupDetail(groupId: string) {
  const group = await db
    .selectFrom("burst_groups as bg")
    .innerJoin("photos as p", (join) => join.on((_eb) => EFFECTIVE_BEST_SHOT))
    .leftJoin("locations as l", "l.id", "p.location_id")
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
      "l.name as locationName",
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

// Chronological neighbors by effective best-shot taken_at — the anchor
// used to drive the group detail page's "merge with previous/next group"
// action (see plan: manual upload / grouping overrides). A group has no
// stored taken_at of its own, so this reuses the same effective-best-shot
// join as everywhere else rather than aggregating min(taken_at) per group.
export async function getAdjacentGroupIds(groupId: string, takenAt: Date) {
  const [prev, next] = await Promise.all([
    db
      .selectFrom("burst_groups as bg")
      .innerJoin("photos as p", (join) => join.on((_eb) => EFFECTIVE_BEST_SHOT))
      .select(["bg.id as groupId", "p.r2_key_thumb as thumbKey"])
      .where("p.taken_at", "<", takenAt)
      .where("bg.id", "!=", groupId)
      .orderBy("p.taken_at", "desc")
      .limit(1)
      .executeTakeFirst(),
    db
      .selectFrom("burst_groups as bg")
      .innerJoin("photos as p", (join) => join.on((_eb) => EFFECTIVE_BEST_SHOT))
      .select(["bg.id as groupId", "p.r2_key_thumb as thumbKey"])
      .where("p.taken_at", ">", takenAt)
      .where("bg.id", "!=", groupId)
      .orderBy("p.taken_at", "asc")
      .limit(1)
      .executeTakeFirst(),
  ]);

  return {
    prevGroupId: prev?.groupId ?? null,
    prevThumbKey: prev?.thumbKey ?? null,
    nextGroupId: next?.groupId ?? null,
    nextThumbKey: next?.thumbKey ?? null,
  };
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
    .leftJoin("locations as l", "l.id", "p.location_id")
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
    .select([
      "bg.id as groupId",
      "p.r2_key_thumb as thumbKey",
      "p.taken_at as takenAt",
      "p.gps_lat as gpsLat",
      "p.gps_lng as gpsLng",
      "l.name as locationName",
    ])
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

    // Reject every existing row regardless of status, not just pending
    // ones — a group can already have a *confirmed* candidate (from an
    // earlier AI-suggestion confirm) by the time someone decides to
    // retype it manually instead. Only filtering on pending_review left
    // that old confirmed row standing, so the group ended up with two
    // confirmed rows at once — the "at most one confirmed" invariant
    // every other query assumes (getConfirmedCandidate's
    // executeTakeFirst() silently picked one; getGalleryGroups's join
    // instead produced two rows for the same group, a real duplicate-
    // React-key bug this surfaced). Typing a species manually is meant
    // to be the definitive answer either way, confirmed or not.
    await trx
      .updateTable("burst_group_species")
      .set({ status: "rejected" })
      .where("burst_group_id", "=", groupId)
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
