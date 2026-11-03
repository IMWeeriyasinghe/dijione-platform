"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

/** Page state kept in the URL query string, so filters survive refreshes,
 *  back/forward navigation and drill-down links (e.g. Overview → Exceptions
 *  with a review flag already applied). Values equal to their default are
 *  omitted to keep URLs short. Updating any filter resets `page` unless the
 *  update sets `page` itself. Defaults may depend on data (e.g. the site's
 *  local "today"), so a URL without that key follows the current default. */
export function useUrlState<T extends Record<string, string>>(defaults: T): [T, (patch: Partial<T>) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const state = { ...defaults };
  for (const k of Object.keys(defaults) as (keyof T)[]) {
    const v = params.get(k as string);
    if (v !== null) state[k] = v as T[keyof T];
  }

  const set = (patch: Partial<T>) => {
    const next = new URLSearchParams(params.toString());
    const merged: Record<string, string | undefined> = { ...state, ...patch };
    if (!("page" in patch) && "page" in defaults) merged.page = defaults.page;
    for (const k of Object.keys(defaults)) {
      const v = merged[k];
      if (v === undefined || v === "" || v === defaults[k]) next.delete(k);
      else next.set(k, v);
    }
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  return [state, set];
}

/** Build an in-app href with query parameters, skipping empty values. */
export function hrefWith(path: string, params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `${path}?${s}` : path;
}
