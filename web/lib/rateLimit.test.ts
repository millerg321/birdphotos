import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Redis and Ratelimit are constructed lazily inside lib/rateLimit.ts
// specifically so mocking them here doesn't need real
// UPSTASH_REDIS_REST_URL/TOKEN env vars — see that file's comment.
const limitMock = vi.fn();
vi.mock("@upstash/ratelimit", () => {
  class MockRatelimit {
    limit = limitMock;
    static slidingWindow = vi.fn();
  }
  return { Ratelimit: MockRatelimit };
});

// A tiny in-memory stand-in for Redis INCR/EXPIRE, keyed like the real
// thing, so checkDailyCap's per-day key behavior is actually exercised
// rather than just asserting a mock was called.
const store = new Map<string, number>();
const fromEnvMock = vi.fn(() => ({
  incr: vi.fn(async (key: string) => {
    const next = (store.get(key) ?? 0) + 1;
    store.set(key, next);
    return next;
  }),
  expire: vi.fn(async () => 1),
}));
vi.mock("@upstash/redis", () => ({
  Redis: { fromEnv: fromEnvMock },
}));

describe("checkIdentifyRateLimit", () => {
  beforeEach(() => {
    limitMock.mockReset();
  });

  it("returns true when the limiter allows the request", async () => {
    limitMock.mockResolvedValueOnce({ success: true });
    const { checkIdentifyRateLimit } = await import("./rateLimit");
    expect(await checkIdentifyRateLimit("1.2.3.4")).toBe(true);
  });

  it("returns false when the limiter blocks the request", async () => {
    limitMock.mockResolvedValueOnce({ success: false });
    const { checkIdentifyRateLimit } = await import("./rateLimit");
    expect(await checkIdentifyRateLimit("1.2.3.4")).toBe(false);
  });

  it("fails closed if Redis errors", async () => {
    limitMock.mockRejectedValueOnce(new Error("upstash unreachable"));
    const { checkIdentifyRateLimit } = await import("./rateLimit");
    expect(await checkIdentifyRateLimit("1.2.3.4")).toBe(false);
  });
});

describe("checkDailyCap", () => {
  beforeEach(() => {
    store.clear();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("allows requests under the cap and blocks once it's exceeded", async () => {
    const { checkDailyCap } = await import("./rateLimit");
    for (let i = 0; i < 100; i++) {
      expect(await checkDailyCap()).toBe(true);
    }
    expect(await checkDailyCap()).toBe(false);
  });

  it("resets once the date rolls over", async () => {
    const { checkDailyCap } = await import("./rateLimit");
    for (let i = 0; i < 100; i++) {
      await checkDailyCap();
    }
    expect(await checkDailyCap()).toBe(false);

    vi.setSystemTime(new Date("2026-01-02T00:00:00Z"));
    expect(await checkDailyCap()).toBe(true);
  });
});
