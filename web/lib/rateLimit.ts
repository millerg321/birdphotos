import { Ratelimit } from "@upstash/ratelimit";
import { Redis } from "@upstash/redis";

// Tunable by hand, not env vars — a personal-scale project doesn't need
// config plumbing for two numbers (see plan: ephemeral photo
// identification). IDENTIFY_DAILY_CAP is the real backstop: it bounds
// worst-case Anthropic spend from /identify regardless of how many
// different IPs an abuser rotates through.
const IDENTIFY_RATE_LIMIT_PER_IP = 5;
const IDENTIFY_RATE_LIMIT_WINDOW = "1 h";
const IDENTIFY_DAILY_CAP = 100;
const DAILY_CAP_KEY_TTL_SECONDS = 60 * 60 * 25; // a day plus margin, not exactly 24h

// Constructed lazily rather than at module scope: this file is imported
// by app/api/identify/route.ts, and Next traces/bundles that import at
// build time regardless of whether the route ever runs — Redis.fromEnv()
// throws immediately if UPSTASH_REDIS_REST_URL/TOKEN aren't set, which
// would otherwise break the build before the Upstash database even
// exists. Only an actual /identify request needs the real credentials.
let redis: Redis | null = null;
function getRedis(): Redis {
  if (!redis) {
    redis = Redis.fromEnv();
  }
  return redis;
}

let ratelimit: Ratelimit | null = null;
function getRatelimit(): Ratelimit {
  if (!ratelimit) {
    ratelimit = new Ratelimit({
      redis: getRedis(),
      limiter: Ratelimit.slidingWindow(IDENTIFY_RATE_LIMIT_PER_IP, IDENTIFY_RATE_LIMIT_WINDOW),
      prefix: "identify-ip",
    });
  }
  return ratelimit;
}

// Vercel's x-forwarded-for, observed in production, isn't a bare IP —
// it can carry a trailing :port (e.g. "95.45.13.96:497060"), and that
// suffix is NOT a fresh per-request ephemeral port: two real, unrelated
// requests produced two DIFFERENT ports for the same IP, then a third
// request landed on one of those exact same ip:port keys again —
// meaning the raw header value was being used directly as the rate-
// limit identifier, so unrelated visitors could exhaust each other's
// limit (or, just as bad, each get a fresh key every time and never be
// limited at all, depending on how that suffix happens to land). Strip
// it so the identifier is the IP alone, which is what "per-IP" means.
// A trailing :digits is stripped whether the address is IPv4 or bare
// IPv6 (e.g. "::1:497060" -> "::1") — the ambiguity that creates for a
// real bracket-less IPv6 address ending in a decimal-looking hex group
// is an acceptable tradeoff here, since this only needs to be "good
// enough" to identify a rate-limit peer, not a general-purpose parser.
export function extractClientIp(forwardedFor: string | null): string {
  return forwardedFor?.split(",")[0]?.trim().replace(/:\d+$/, "") ?? "unknown";
}

// Fails closed on any Redis error: this is the abuse/budget backstop for
// a real per-request Anthropic API call, so an outage here should block
// requests rather than silently let them all through.
export async function checkIdentifyRateLimit(ip: string): Promise<boolean> {
  try {
    const { success } = await getRatelimit().limit(ip);
    return success;
  } catch {
    return false;
  }
}

export async function checkDailyCap(): Promise<boolean> {
  const today = new Date().toISOString().slice(0, 10);
  try {
    const count = await getRedis().incr(`identify-daily:${today}`);
    if (count === 1) {
      await getRedis().expire(`identify-daily:${today}`, DAILY_CAP_KEY_TTL_SECONDS);
    }
    return count <= IDENTIFY_DAILY_CAP;
  } catch {
    return false;
  }
}
