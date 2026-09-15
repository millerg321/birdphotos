import { describe, expect, it } from "vitest";
import { clampIndex } from "./GalleryGrid";

describe("clampIndex", () => {
  it("moves forward and backward within bounds", () => {
    expect(clampIndex(2, 1, 5)).toBe(3);
    expect(clampIndex(2, -1, 5)).toBe(1);
  });

  it("clamps at the last index rather than wrapping around", () => {
    expect(clampIndex(4, 1, 5)).toBe(4);
  });

  it("clamps at zero rather than wrapping around", () => {
    expect(clampIndex(0, -1, 5)).toBe(0);
  });

  it("handles a single-item list", () => {
    expect(clampIndex(0, 1, 1)).toBe(0);
    expect(clampIndex(0, -1, 1)).toBe(0);
  });

  it("returns the current index unchanged for an empty list", () => {
    expect(clampIndex(0, 1, 0)).toBe(0);
  });
});
