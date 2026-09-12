import { describe, expect, it } from "vitest";
import { wikipediaSearchUrl } from "./wikipedia";

describe("wikipediaSearchUrl", () => {
  it("builds a Special:Search URL", () => {
    expect(wikipediaSearchUrl("Barn Owl")).toBe(
      "https://en.wikipedia.org/wiki/Special:Search?search=Barn%20Owl",
    );
  });

  it("encodes special characters", () => {
    expect(wikipediaSearchUrl("Great Spotted Woodpecker & Co")).toContain(
      encodeURIComponent("Great Spotted Woodpecker & Co"),
    );
  });
});
