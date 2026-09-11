// Kept dependency-free (no next/server, no next-auth) so it can be unit
// tested directly without pulling in the proxy's runtime imports.
const PUBLIC_PATHS = ["/login", "/api/auth"];

export function isPublicPath(pathname: string): boolean {
  return (
    PUBLIC_PATHS.some((path) => pathname.startsWith(path)) ||
    pathname.startsWith("/s/")
  );
}
