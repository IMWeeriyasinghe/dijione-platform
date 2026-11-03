"use client";

export const PAGE_SIZES = [10, 20, 50, 100] as const;
export const DEFAULT_PAGE_SIZE = 10;
const KEY = (view: string) => `onsite.pageSize.${view}`;

/** The user's chosen page size for a view (a number only — no attendance
 *  data is ever kept in browser storage). Falls back to 10. */
export function storedPageSize(view: string): string {
  try {
    const v = Number(window.localStorage.getItem(KEY(view)));
    return (PAGE_SIZES as readonly number[]).includes(v) ? String(v) : String(DEFAULT_PAGE_SIZE);
  } catch {
    return String(DEFAULT_PAGE_SIZE);
  }
}

export function rememberPageSize(view: string, size: number): void {
  try {
    window.localStorage.setItem(KEY(view), String(size));
  } catch {
    /* private mode etc. — the URL still carries the choice */
  }
}

export function parsePageSize(v: string): number {
  const n = Number(v);
  return (PAGE_SIZES as readonly number[]).includes(n) ? n : DEFAULT_PAGE_SIZE;
}
