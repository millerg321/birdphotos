import { describe, expect, it } from "vitest";
import { formatCamera, formatExposure } from "./formatExif";

describe("formatExposure", () => {
  it("joins all three parts", () => {
    expect(formatExposure(6.9, "1/200s", 250)).toBe("f/6.9 · 1/200s · ISO 250");
  });

  it("omits missing parts", () => {
    expect(formatExposure(null, "1/200s", null)).toBe("1/200s");
  });

  it("falls back to an em dash when nothing is known", () => {
    expect(formatExposure(null, null, null)).toBe("—");
  });
});

describe("formatCamera", () => {
  it("avoids duplicating the make when the model already includes it", () => {
    expect(formatCamera("Canon", "Canon PowerShot SX740 HS")).toBe(
      "Canon PowerShot SX740 HS",
    );
  });

  it("joins make and model when the model doesn't repeat the make", () => {
    expect(formatCamera("Nikon", "D850")).toBe("Nikon D850");
  });

  it("falls back to an em dash when both are missing", () => {
    expect(formatCamera(null, null)).toBe("—");
  });

  it("handles a model with no make", () => {
    expect(formatCamera(null, "D850")).toBe("D850");
  });
});
