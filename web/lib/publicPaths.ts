// Kept dependency-free (no next/server, no next-auth) so it can be unit
// tested directly without pulling in the proxy's runtime imports.
//
// /gallery and /identify are intentionally public (see plan: ephemeral
// photo identification) — /gallery's own page component still calls
// auth() itself to decide between the full owner view and the
// simplified anonymous one, this only controls whether the proxy lets
// the request through at all. /identify's own API route
// (/api/identify) additionally rate-limits and cost-caps, since unlike
// every other public path here it triggers a real Anthropic API call.
// /species is public too (see plan: Phase 5 — species pages), a
// shareable field guide of what's been seen. Its detail page still
// calls auth() itself, same reason as /gallery — GalleryGrid's
// owner-only badges/actions need to know isOwner.
const PUBLIC_PATHS = [
  "/login",
  "/api/auth",
  "/gallery",
  "/identify",
  "/api/identify",
  "/species",
];

export function isPublicPath(pathname: string): boolean {
  return (
    PUBLIC_PATHS.some((path) => pathname.startsWith(path)) ||
    pathname.startsWith("/s/")
  );
}
