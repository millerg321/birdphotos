import { describe, expect, it } from "vitest";
import { filterLocations } from "./LocationAutocomplete";

describe("filterLocations", () => {
  const options = ["London, UK", "Ireland", "Borneo", "South Africa"];

  it("returns nothing for an empty query", () => {
    expect(filterLocations(options, "")).toEqual([]);
    expect(filterLocations(options, "   ")).toEqual([]);
  });

  it("matches case-insensitively", () => {
    expect(filterLocations(options, "london")).toEqual(["London, UK"]);
  });

  it("matches a substring anywhere in the name, not just a prefix", () => {
    expect(filterLocations(options, "africa")).toEqual(["South Africa"]);
  });

  it("returns every match when there are several", () => {
    expect(filterLocations(["Ireland", "Iceland"], "l")).toEqual(["Ireland", "Iceland"]);
  });

  it("returns an empty list when nothing matches", () => {
    expect(filterLocations(options, "xyzzy")).toEqual([]);
  });

  it("caps at 8 suggestions", () => {
    const many = Array.from({ length: 20 }, (_, i) => `Place ${i}`);
    expect(filterLocations(many, "place")).toHaveLength(8);
  });
});
