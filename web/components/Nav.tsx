"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/gallery", label: "Gallery" },
  { href: "/upload", label: "Upload" },
  { href: "/review", label: "Review" },
];

// Client component so it can read the current path to highlight the
// active link and hide itself on /login — there's nothing to navigate
// to yet before signing in, and showing links to protected pages there
// reads oddly on a screen that's otherwise just a sign-in button.
export function Nav() {
  const pathname = usePathname();
  if (pathname === "/login") {
    return null;
  }

  return (
    <nav className="flex items-center gap-6 border-b border-zinc-200 bg-zinc-50 px-6 py-3 dark:border-zinc-800 dark:bg-black">
      <Link href="/gallery" className="text-sm font-semibold text-black dark:text-zinc-50">
        Bird Photos
      </Link>
      <div className="flex gap-4 text-sm">
        {LINKS.map((link) => {
          // /groups/[id] counts as "Gallery" too — that's where it's
          // always navigated to from, and there's no separate nav entry
          // for group detail pages.
          const isActive =
            pathname === link.href ||
            pathname?.startsWith(`${link.href}/`) ||
            (link.href === "/gallery" && pathname?.startsWith("/groups/"));
          return (
            <Link
              key={link.href}
              href={link.href}
              className={
                isActive
                  ? "font-medium text-black dark:text-zinc-50"
                  : "text-zinc-500 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-50"
              }
            >
              {link.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
