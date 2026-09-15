"use client";

import { useState, type KeyboardEvent } from "react";

const MAX_SUGGESTIONS = 8;

// Pure and exported for direct unit testing (see
// LocationAutocomplete.test.ts) — same reasoning as GalleryGrid.tsx's
// clampIndex: nothing server-side needs this, only this component,
// client-side, and Vitest doesn't enforce Next's RSC rule against
// importing from a "use client" file, so a plain test file can import
// it straight from here without the split lib/galleryFilters.ts needed
// for buildFilterUrl (which a Server Component genuinely did need to
// call directly).
export function filterLocations(options: string[], query: string): string[] {
  const trimmed = query.trim().toLowerCase();
  if (trimmed === "") {
    return [];
  }
  return options
    .filter((name) => name.toLowerCase().includes(trimmed))
    .slice(0, MAX_SUGGESTIONS);
}

// Filters `options` client-side, no network call — see plan: location
// autocomplete. `options` is the full known-locations list (small,
// fetched once by the page and passed down), not fetched per keystroke.
export function LocationAutocomplete({
  value,
  onValueChange,
  onSelect,
  options,
  placeholder,
  disabled,
  className,
  id,
  maxLength,
}: {
  value: string;
  onValueChange: (value: string) => void;
  onSelect: (name: string) => void;
  options: string[];
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  id?: string;
  maxLength?: number;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(0);

  const matches = filterLocations(options, value);
  // Clamped at use time rather than kept in sync via an effect — matches
  // shrinks as the user types, and a stale index just needs to not point
  // past the end of the new (shorter) list.
  const safeIndex = Math.min(highlightedIndex, matches.length - 1);

  function handleSelect(name: string) {
    onSelect(name);
    setIsOpen(false);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!isOpen || matches.length === 0) {
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex(Math.min(safeIndex + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex(Math.max(safeIndex - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      handleSelect(matches[safeIndex]);
    } else if (e.key === "Escape") {
      setIsOpen(false);
    }
  }

  return (
    <div className="relative">
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => {
          onValueChange(e.target.value);
          setIsOpen(true);
          setHighlightedIndex(0);
        }}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setIsOpen(false)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        maxLength={maxLength}
        className={className}
      />
      {isOpen && matches.length > 0 && (
        <ul className="absolute z-10 mt-1 max-h-48 w-max min-w-full overflow-auto rounded-md border border-zinc-300 bg-white text-xs shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          {matches.map((name, index) => (
            <li key={name}>
              <button
                type="button"
                // mousedown, not click: fires before the input's onBlur,
                // so the selection registers before the dropdown would
                // otherwise already have closed — the standard combobox
                // ordering fix. preventDefault also stops the input from
                // losing focus at all when a suggestion is clicked.
                onMouseDown={(e) => {
                  e.preventDefault();
                  handleSelect(name);
                }}
                className={`block w-full px-2 py-1 text-left text-black dark:text-zinc-50 ${
                  index === safeIndex ? "bg-zinc-100 dark:bg-zinc-800" : ""
                }`}
              >
                {name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
