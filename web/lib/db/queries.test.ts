import { describe, expect, it } from "vitest";
import { slugify } from "./queries";

describe("slugify", () => {
  it("lowercases and hyphenates", () => {
    expect(slugify("Ring-necked Parakeet")).toBe("ring-necked-parakeet");
  });

  // The actual bug this guards against: getOrCreateSpeciesId's existing-row
  // check matched on common_name (exact, modulo case), but the DB's real
  // uniqueness boundary is the slug — which normalizes away punctuation
  // and whitespace differences the common_name check didn't catch. Two
  // "different" typed names colliding here is exactly what crashed
  // production with a duplicate-key error on species_slug_key.
  it("produces the same slug for punctuation/whitespace variants", () => {
    expect(slugify("Ring necked Parakeet")).toBe(slugify("Ring-necked Parakeet"));
    expect(slugify("Ring-necked  Parakeet")).toBe(slugify("Ring-necked Parakeet"));
  });

  it("falls back to unknown for an all-punctuation input", () => {
    expect(slugify("...")).toBe("unknown");
  });
});
