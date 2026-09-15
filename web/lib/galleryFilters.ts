export interface GalleryFilters {
  filter?: string | null;
  species?: string | null;
  from?: string | null;
  to?: string | null;
}

// Kept out of GalleryFilterBar.tsx deliberately: that file is "use
// client", and Next's RSC boundary won't let a Server Component call
// *any* export from a client module directly — even a plain, pure
// function — only render it as a component or pass it as props. This
// needs to be callable from both app/gallery/page.tsx (a Server
// Component, for the All/Needs-review links' hrefs) and
// GalleryFilterBar.tsx itself, so it lives in its own plain module.
//
// Takes every currently-active param as plain values (rather than
// reading them client-side via useSearchParams) since the server
// component already knows all of them from its own searchParams prop —
// merges in `updates` (a null/empty value clears that param) and drops
// anything falsy. Same query-param-driven filtering model the existing
// All/Needs-review links already used before this, just needs to be
// JS-driven for the pieces (<select>, date inputs) that can't be a
// plain <Link>.
export function buildFilterUrl(current: GalleryFilters, updates: GalleryFilters): string {
  const merged = { ...current, ...updates };
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(merged)) {
    if (value) {
      params.set(key, value);
    }
  }
  const query = params.toString();
  return query ? `/gallery?${query}` : "/gallery";
}
