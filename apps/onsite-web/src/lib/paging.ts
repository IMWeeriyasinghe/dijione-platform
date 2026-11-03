"use client";

import { useEffect } from "react";
import { parsePageSize, rememberPageSize } from "./page-size";

/** Page + page size from URL state. Changing the size remembers it for this
 *  view and returns to page 1; if a refresh or filter leaves the current page
 *  past the end, it moves to the last valid page. */
export function usePaging(view: string, s: { page: string; size: string }, set: (p: { page?: string; size?: string }) => void,
  total: number | undefined) {
  const page = Math.max(1, Number(s.page) || 1);
  const size = parsePageSize(s.size);
  useEffect(() => {
    if (total === undefined || total === 0) return;
    const pages = Math.ceil(total / size);
    if (page > pages) set({ page: String(pages) });
  }, [total, size, page, set]);
  return {
    page,
    size,
    onPage: (p: number) => set({ page: String(p) }),
    onPageSize: (n: number) => {
      rememberPageSize(view, n);
      set({ size: String(n) });
    },
  };
}
