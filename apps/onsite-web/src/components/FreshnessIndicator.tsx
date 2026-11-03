"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { getFreshness } from "@/lib/api";
import { FEED_LABEL, FEED_TONE } from "@/lib/format";
import { liveQuery } from "@/lib/live-refresh";
import { ToneBadge } from "./ToneBadge";

/** The minimal shape of a TanStack query result this indicator reports on. */
export type RefreshableQuery = {
  dataUpdatedAt: number;
  isFetching: boolean;
  isError: boolean;
  refetch: () => unknown;
};

export function ago(fromMs: number, nowMs: number): string {
  const s = Math.max(0, Math.round((nowMs - fromMs) / 1000));
  if (s < 10) return "just now";
  if (s < 60) return `${Math.floor(s / 10) * 10} seconds ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} hour${h === 1 ? "" : "s"} ago`;
  return `${Math.floor(h / 24)} days ago`;
}

function useNow(tickMs = 5_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), tickMs);
    return () => clearInterval(t);
  }, [tickMs]);
  return now;
}

/** Small freshness strip. It keeps two facts apart: when this page last
 *  refreshed (frontend refetch) and when DijiOne last mirrored the attendance
 *  source (backend sync). A successful page refresh never implies the source
 *  is current — the mirror state comes from /api/onsite/freshness. */
export function FreshnessIndicator({ siteId, queries }: { siteId: string; queries: RefreshableQuery[] }) {
  const now = useNow();
  const fresh = useQuery({ queryKey: ["onsite-freshness", siteId], queryFn: () => getFreshness(siteId), ...liveQuery });
  const all = [...queries, fresh];
  const loaded = queries.map((q) => q.dataUpdatedAt).filter((t) => t > 0);
  const pageUpdated = loaded.length ? Math.min(...loaded) : 0;
  const fetching = all.some((q) => q.isFetching);
  const refreshFailed = queries.some((q) => q.isError && q.dataUpdatedAt > 0);

  const site = fresh.data?.sites.find((s) => s.site_id === siteId);
  const feed = site?.feed_state ?? "NOT_SYNCED";
  const lastSync = fresh.data?.last_successful_sync_at ? Date.parse(fresh.data.last_successful_sync_at) : null;
  const delayed = fresh.isError || feed !== "FRESH";

  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-dt-text-secondary"
      role="status"
      aria-live="polite"
      data-testid="freshness-indicator"
    >
      <ToneBadge tone={FEED_TONE[feed]}>{FEED_LABEL[feed]}</ToneBadge>
      <span>{pageUpdated ? `Updated ${ago(pageUpdated, now)}` : "Loading…"}</span>
      <span>{lastSync ? `Last synced ${ago(lastSync, now)}` : "Not yet synced"}</span>
      {delayed && <span className="text-dt-burnt-orange">Data may be delayed</span>}
      {refreshFailed && <span className="text-dt-danger">Refresh failed — showing the last loaded data</span>}
      <button
        type="button"
        onClick={() => all.forEach((q) => q.refetch())}
        disabled={fetching}
        className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium text-dt-burnt-orange hover:bg-dt-surface-warm disabled:opacity-60"
        aria-label="Refresh now"
      >
        <RefreshCw className={`h-3.5 w-3.5 ${fetching ? "animate-spin" : ""}`} aria-hidden />
        Refresh
      </button>
    </div>
  );
}
