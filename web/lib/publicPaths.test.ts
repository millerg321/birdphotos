import { describe, expect, it } from "vitest";
import { isPublicPath } from "./publicPaths";

describe("isPublicPath", () => {
  it("allows the login page", () => {
    expect(isPublicPath("/login")).toBe(true);
  });

  it("allows NextAuth API routes", () => {
    expect(isPublicPath("/api/auth/callback/google")).toBe(true);
  });

  it("allows share links", () => {
    expect(isPublicPath("/s/abc123")).toBe(true);
  });

  it("blocks the gallery", () => {
    expect(isPublicPath("/gallery")).toBe(false);
  });

  it("blocks the review queue", () => {
    expect(isPublicPath("/review")).toBe(false);
  });
});
