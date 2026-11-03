"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { getFreshness } from "@/lib/api";
import { FEED_LABEL, FEED_TONE } from "@/lib/format";
import { liveQuery } from "@/lib/live-refresh";
import { hasPermission, PERM, useOnsiteScope } from "@/lib/onsite-scope";
import type { FeedState } from "@/lib/types";
import { cx, focusRing } from "./kit";
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

const EXPLAIN: Partial<Record<FeedState, string>> = {
  DELAYED: "DijiOne has not completed a mirror sync for a few minutes, or the Agent has deliveries pending. Recent punches may not be shown yet.",
  STALE: "The Diji On-site Agent has not sent a heartbeat recently. New punches may not be reaching Diji On-site Attendance.",
  SOURCE_UNAVAILABLE: "The latest mirror sync could not reach Diji On-site Attendance. Data shown is the last successfully mirrored copy.",
  NOT_SYNCED: "DijiOne has not mirrored this source yet.",
};

/** Small freshness strip. It keeps four facts apart: when this page last
 *  refreshed (frontend), when DijiOne last mirrored the source (backend sync),
 *  the latest event the source received, and the Agent heartbeat. A successful
 *  page refresh never implies the source is current — the mirror state comes
 *  from /api/onsite/freshness. Normal operation stays one quiet line. */
export function FreshnessIndicator({ siteId, queries }: { siteId: string; queries: RefreshableQuery[] }) {
  const now = useNow();
  const { scope } = useOnsiteScope();
  const fresh = useQuery({ queryKey: ["onsite-freshness", siteId], queryFn: () => getFreshness(siteId), ...liveQuery });
  const all = [...queries, fresh];
  const loaded = queries.map((q) => q.dataUpdatedAt).filter((t) => t > 0);
  const pageUpdated = loaded.length ? Math.min(...loaded) : 0;
  const fetching = all.some((q) => q.isFetching);
  const refreshFailed = queries.some((q) => q.isError && q.dataUpdatedAt > 0);

  const site = fresh.data?.sites.find((s) => s.site_id === siteId);
  const feed: FeedState = site?.feed_state ?? "NOT_SYNCED";
  const lastSync = fresh.data?.last_successful_sync_at ? Date.parse(fresh.data.last_successful_sync_at) : null;
  const received = site?.latest_received_utc ? Date.parse(site.latest_received_utc) : null;
  const heartbeat = site?.agent_heartbeat_utc ? Date.parse(site.agent_heartbeat_utc) : null;
  const delayed = fresh.isError || feed !== "FRESH";

  return (
    <div className="space-y-2" data-testid="freshness-indicator">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-dt-border/70 bg-dt-surface px-3 py-1.5 text-xs text-dt-text-secondary"
        role="status" aria-live="polite">
        <ToneBadge tone={FEED_TONE[feed]}>{FEED_LABEL[feed]}</ToneBadge>
        <span>{pageUpdated ? `Updated ${ago(pageUpdated, now)}` : "Loading…"}</span>
        <span>{lastSync ? `Last synced ${ago(lastSync, now)}` : "Not yet synced"}</span>
        {received && <span className="hidden sm:inline">Latest event received {ago(received, now)}</span>}
        {heartbeat && <span className="hidden lg:inline">Agent heartbeat {ago(heartbeat, now)}</span>}
        {delayed && <span className="font-medium text-dt-burnt-orange">Data may be delayed</span>}
        {refreshFailed && <span className="font-medium text-dt-danger">Refresh failed — showing the last loaded data</span>}
        <button type="button" onClick={() => all.forEach((q) => q.refetch())} disabled={fetching} aria-label="Refresh now"
          className={cx("ml-auto inline-flex min-h-8 items-center gap-1 rounded-md px-2 font-medium text-dt-burnt-orange hover:bg-dt-surface-warm disabled:opacity-60", focusRing)}>
          <RefreshCw className={cx("size-3.5", fetching && "motion-safe:animate-spin")} aria-hidden />
          Refresh
        </button>
      </div>
      {fresh.data && EXPLAIN[feed] && (
        <p className="rounded-lg border border-dt-amber/40 bg-dt-amber/10 px-3 py-2 text-xs text-dt-text-primary">
          {EXPLAIN[feed]} Treat “no activity” with care until the feed is current.
          {hasPermission(scope, PERM.HEALTH) && (
            <> <Link href="/admin/health" className="-my-2 inline-block py-2 font-medium text-dt-burnt-orange underline underline-offset-2">Open Site Health</Link></>
          )}
        </p>
      )}
    </div>
  );
}
