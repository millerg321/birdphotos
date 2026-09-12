// Special:Search (rather than a direct /wiki/<title> link) redirects
// straight to the article when there's a close/exact match, but degrades
// gracefully to a search results page otherwise — direct /wiki/ links
// 404 outright on the smallest title mismatch (capitalization, hyphens),
// which is common with multi-word bird common names.
export function wikipediaSearchUrl(query: string): string {
  return `https://en.wikipedia.org/wiki/Special:Search?search=${encodeURIComponent(query)}`;
}
