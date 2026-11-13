"use client";

import { useCallback, useEffect, useState } from "react";

export const SEARCH_DEBOUNCE_MS = 300;
export const CARD_PAGE_SIZES = [12, 24, 48, 96] as const;
export const TABLE_PAGE_SIZES = [20, 50, 100] as const;

/**
 * Page + page-size state for a server-paginated list. Changing the page
 * size, a filter (`reset()`), or the committed search always returns to
 * page 1 while keeping the chosen page size.
 */
export function usePaging(defaultPageSize: number) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSizeState] = useState(defaultPageSize);
  const setPageSize = useCallback((size: number) => {
    setPageSizeState(size);
    setPage(1);
  }, []);
  const reset = useCallback(() => setPage(1), []);
  return { page, pageSize, setPage, setPageSize, reset };
}

/**
 * Debounced search box state: `input` follows every keystroke, `search`
 * (what you send to the API) commits after a pause. `onCommit` runs when a
 * new term commits — pass `paging.reset` so a new search starts at page 1.
 */
export function useDebouncedSearch(onCommit: () => void, initial = "") {
  const [input, setInput] = useState(initial);
  const [search, setSearch] = useState(initial.trim());
  useEffect(() => {
    const next = input.trim();
    if (next === search) return;
    const t = setTimeout(() => {
      setSearch(next);
      onCommit();
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [input, search, onCommit]);
  return { input, setInput, search };
}

/** Keep the previous page on screen only while paging the SAME query —
 * a new search/filter never shows the old results as if current. */
export function keepPageWhile<T>(sameQuery: (prevKey: readonly unknown[]) => boolean) {
  return (previous: T | undefined, previousQuery: { queryKey: readonly unknown[] } | undefined) =>
    previousQuery && sameQuery(previousQuery.queryKey) ? previous : undefined;
}
