import { describe, expect, it } from "vitest";
import { buildFilterUrl } from "./galleryFilters";

describe("buildFilterUrl", () => {
  it("returns the bare path with no active filters", () => {
    expect(buildFilterUrl({}, {})).toBe("/gallery");
  });

  it("sets a new filter", () => {
    expect(buildFilterUrl({}, { species: "eurasian-blue-tit" })).toBe(
      "/gallery?species=eurasian-blue-tit",
    );
  });

  it("preserves existing filters not mentioned in the update", () => {
    const current = { filter: "unreviewed", species: "eurasian-blue-tit" };
    expect(buildFilterUrl(current, { from: "2024-01-01" })).toBe(
      "/gallery?filter=unreviewed&species=eurasian-blue-tit&from=2024-01-01",
    );
  });

  it("a null update clears that filter", () => {
    const current = { species: "eurasian-blue-tit", from: "2024-01-01" };
    expect(buildFilterUrl(current, { species: null })).toBe("/gallery?from=2024-01-01");
  });

  it("an empty-string update also clears that filter", () => {
    const current = { species: "eurasian-blue-tit" };
    expect(buildFilterUrl(current, { species: "" })).toBe("/gallery");
  });

  it("clearing every filter at once returns the bare path", () => {
    const current = { filter: "unreviewed", species: "eurasian-blue-tit", from: "2024-01-01" };
    expect(buildFilterUrl(current, { species: null, from: null })).toBe(
      "/gallery?filter=unreviewed",
    );
  });

  it("sort behaves like any other param — set, preserved, and clearable", () => {
    expect(buildFilterUrl({}, { sort: "sharpest" })).toBe("/gallery?sort=sharpest");

    const current = { species: "eurasian-blue-tit", sort: "sharpest" };
    // Clearing species doesn't touch sort — "Clear filters" only clears
    // species/from/to (see GalleryFilterBar.tsx), sort is "how it's
    // ordered," not "what's shown."
    expect(buildFilterUrl(current, { species: null })).toBe("/gallery?sort=sharpest");
    expect(buildFilterUrl(current, { sort: null })).toBe("/gallery?species=eurasian-blue-tit");
  });
});
