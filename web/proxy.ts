import { auth } from "@/lib/auth";
import { isPublicPath } from "@/lib/publicPaths";
import { NextResponse } from "next/server";

// Everything is gated except the login page, the NextAuth API routes, and
// the public share-link view (see plan: Auth & Sharing).
export default auth((req) => {
  const { pathname } = req.nextUrl;

  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  if (!req.auth) {
    const loginUrl = new URL("/login", req.nextUrl.origin);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
