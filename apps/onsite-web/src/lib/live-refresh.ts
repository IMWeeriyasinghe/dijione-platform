import { keepPreviousData } from "@tanstack/react-query";

/** Dashboard refetch cadence. The mirror itself syncs every minute
 *  (onsite-sync-job `* * * * *`), so new punches appear within ~1–2 minutes. */
export const LIVE_REFRESH_MS = 30_000;

/** TanStack Query options for attendance views where freshness matters:
 *  - refetch every 30 s while the tab is visible (paused in the background),
 *    and immediately when the tab becomes active again;
 *  - keep the previous result while a refetch or a filter/page change loads,
 *    so the page never flashes back to a full loading state;
 *  - a failed refetch keeps the last valid data (TanStack never clears
 *    `data` on error) — pages render the error only when nothing was loaded.
 *  TanStack dedupes identical in-flight queries and ignores results for keys
 *  that are no longer observed. Never use this for admin edit forms. */
export const liveQuery = {
  refetchInterval: LIVE_REFRESH_MS,
  refetchIntervalInBackground: false,
  refetchOnWindowFocus: true,
  staleTime: LIVE_REFRESH_MS / 2,
  placeholderData: keepPreviousData,
} as const;
