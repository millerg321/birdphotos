import { describe, expect, it, vi } from "vitest";
import { redirect } from "next/navigation";
import Home from "./page";

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
}));

describe("Home", () => {
  it("redirects to the gallery", () => {
    Home();
    expect(redirect).toHaveBeenCalledWith("/gallery");
  });
});
