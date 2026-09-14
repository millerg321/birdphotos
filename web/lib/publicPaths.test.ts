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

  it("allows the gallery", () => {
    expect(isPublicPath("/gallery")).toBe(true);
  });

  it("allows the identify page and its API route", () => {
    expect(isPublicPath("/identify")).toBe(true);
    expect(isPublicPath("/api/identify")).toBe(true);
  });

  it("blocks the review queue", () => {
    expect(isPublicPath("/review")).toBe(false);
  });

  it("blocks the upload page", () => {
    expect(isPublicPath("/upload")).toBe(false);
  });

  it("blocks group detail", () => {
    expect(isPublicPath("/groups/abc123")).toBe(false);
  });
});
