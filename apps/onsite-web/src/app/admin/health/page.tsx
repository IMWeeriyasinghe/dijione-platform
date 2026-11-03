"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { Clock, Database, HeartPulse, Inbox, Radio, ServerCog } from "lucide-react";
import { AdminOnly } from "@/components/AdminOnly";
import { DataView, Facts } from "@/components/DataView";
import { ago } from "@/components/FreshnessIndicator";
import { InlineAlert, KpiCard, PageTop, Panel, SkeletonRows } from "@/components/kit";
import { SyncNowButton } from "@/components/SyncNowButton";
import { ToneBadge } from "@/components/ToneBadge";
import { getHealth, getSyncHistory } from "@/lib/api";
import { FEED_LABEL, FEED_TONE, formatDateTime } from "@/lib/format";
import { liveQuery } from "@/lib/live-refresh";
import { PERM } from "@/lib/onsite-scope";
import { fmtNum } from "@/lib/period";
import type { FeedState, SyncRun } from "@/lib/types";

const RECOVERY: Partial<Record<FeedState, string>> = {
  SOURCE_UNAVAILABLE: "DijiOne could not reach Diji On-site Attendance on the latest sync. The mirror is unchanged; the next one-minute sync retries automatically. If this persists, check the Azure SQL database status, then use Sync now.",
  STALE: "The Diji On-site Agent has not sent a heartbeat recently. Check that the Agent Windows service is running on the site PC and that it can reach the ingestion endpoint.",
  DELAYED: "Mirror syncs are late or the Agent has pending deliveries. Syncs run every minute; if this lasts more than a few minutes, check recent sync runs below.",
  NOT_SYNCED: "No successful mirror sync yet. Use Sync now to run the first one.",
};

function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 5_000); return () => clearInterval(t); }, []);
  return now;
}

const since = (iso: string | null | undefined, now: number) => (iso ? ago(Date.parse(iso), now) : "—");

function HealthView() {
  const queryClient = useQueryClient();
  const now = useNow();
  const health = useQuery({ queryKey: ["onsite-health"], queryFn: getHealth, ...liveQuery });
  const history = useQuery({ queryKey: ["onsite-sync-history"], queryFn: getSyncHistory, ...liveQuery });

  if (health.isLoading) return <SkeletonRows label="Loading site health…" />;
  if (!health.data) return <ErrorState onRetry={() => health.refetch()} />;
  const data = health.data;
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["onsite-health"] });
    queryClient.invalidateQueries({ queryKey: ["onsite-sync-history"] });
  };
  const worst = data.sites.map((s) => s.feed_state).find((f) => f !== "FRESH");

  return (
    <div className="space-y-4">
      <PageTop
        title="Site Health"
        description="Attendance feed, Diji On-site Agent heartbeat, DijiOne mirror sync (every minute) and source-to-mirror reconciliation."
        actions={data.source_configured === false ? undefined : <SyncNowButton onDone={refresh} />}
      />

      {data.source_configured === false && (
        <InlineAlert tone="info">
          <span className="font-medium">No attendance source is configured for this environment.</span>{" "}
          The application is running, but no attendance feed is connected, so nothing is synced and no attendance data is shown.
          This is expected until an attendance source is provisioned and validated.
        </InlineAlert>
      )}
      {worst && RECOVERY[worst] && <InlineAlert tone={worst === "DELAYED" ? "warning" : "danger"}>{RECOVERY[worst]}</InlineAlert>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="Last mirror sync" value={<span className="text-lg">{since(data.last_successful_sync_at, now)}</span>} icon={Database}
          tone={data.latest_run?.status === "FAILED" ? "danger" : "success"} sub={formatDateTime(data.last_successful_sync_at)}
          help="When DijiOne last completed a mirror sync from Diji On-site Attendance (scheduled every minute)." />
        <KpiCard label="Latest run" value={<span className="text-lg">{data.latest_run?.status ?? "—"}</span>} icon={ServerCog}
          tone={data.latest_run?.status === "FAILED" ? "danger" : "default"}
          sub={data.latest_run?.source_unavailable ? <span className="text-dt-danger">Source unavailable</span> : data.latest_run?.error_summary ?? undefined} />
        <KpiCard label="Latest event received" value={<span className="text-lg">{since(data.sites[0]?.latest_received_utc, now)}</span>} icon={Inbox}
          help="When Diji On-site Attendance received the newest event now in the mirror." sub={formatDateTime(data.sites[0]?.latest_received_utc)} />
        <KpiCard label="Agent heartbeat" value={<span className="text-lg">{since(data.sites[0]?.agent_heartbeat_utc, now)}</span>} icon={HeartPulse}
          tone={data.sites[0]?.feed_state === "STALE" ? "danger" : "default"} help="The Agent reports every 60 seconds, even when nobody punches."
          sub={data.sites[0]?.agent_health ?? undefined} />
      </div>

      <Panel title="Enabled sites" subtitle="Feed state and Diji On-site Agent status per site">
        {data.sites.length === 0 ? (
          <p className="text-sm text-dt-text-secondary">No enabled sites. Enable one from Admin → Sites.</p>
        ) : (
          <DataView caption="Enabled sites" rows={data.sites} rowKey={(s) => s.site_id}
            columns={[
              { key: "site", header: "Site", cell: (s) => <span className="font-medium">{s.site_id}</span> },
              { key: "feed", header: "Feed", cell: (s) => <ToneBadge tone={FEED_TONE[s.feed_state]}>{FEED_LABEL[s.feed_state]}</ToneBadge> },
              { key: "rec", header: "Latest received", cell: (s) => formatDateTime(s.latest_received_utc) },
              { key: "hb", header: "Agent heartbeat", cell: (s) => formatDateTime(s.agent_heartbeat_utc) },
              { key: "pend", header: "Pending", align: "right", cell: (s) => s.agent?.pending_count ?? "—" },
              { key: "dead", header: "Dead-letter", align: "right", cell: (s) => s.agent?.dead_letter_count ?? "—" },
              { key: "err", header: "Last error", minWidth: "xl", cell: (s) => s.agent?.last_error ?? "—" },
            ]}
            card={(s) => (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-dt-text-primary">{s.site_id}</span>
                  <ToneBadge tone={FEED_TONE[s.feed_state]}>{FEED_LABEL[s.feed_state]}</ToneBadge>
                </div>
                <Facts items={[["Latest received", formatDateTime(s.latest_received_utc)], ["Agent heartbeat", formatDateTime(s.agent_heartbeat_utc)],
                  ["Pending", s.agent?.pending_count ?? "—"], ["Dead-letter", s.agent?.dead_letter_count ?? "—"]]} />
                {s.agent?.last_error && <p className="text-xs text-dt-danger">{s.agent.last_error}</p>}
              </div>
            )}
            detail={(s) => s.agent ? (
              <Facts cols={4} items={[["Agent version", s.agent.agent_version ?? "—"], ["Health reason", s.agent.health_reason ?? "—"],
                ["Source epoch", s.agent.source_epoch], ["High-water id", s.agent.high_water_id ?? "—"],
                ["Source connected", s.agent.source_connected ? "Yes" : "No"], ["Last delivery", formatDateTime(s.agent.last_delivery_utc)],
                ["Oldest pending", s.agent.oldest_pending_age_seconds != null ? `${Math.round(s.agent.oldest_pending_age_seconds)} s` : "—"]]} />
            ) : <p className="text-sm text-dt-text-secondary">No Agent status reported.</p>} />
        )}
      </Panel>

      <Panel title="Reconciliation (source vs mirror)" subtitle="Event counts per site and source epoch. Checked whenever a sync adds events, and at least every 15 minutes.">
        {data.reconciliation.length === 0 ? (
          <p className="text-sm text-dt-text-secondary">No successful sync yet.</p>
        ) : (
          <DataView caption="Reconciliation" rows={data.reconciliation} rowKey={(r) => `${r.site_id}-${r.source_epoch}`}
            columns={[
              { key: "site", header: "Site", cell: (r) => r.site_id },
              { key: "epoch", header: "Epoch", align: "right", cell: (r) => r.source_epoch },
              { key: "src", header: "Source", align: "right", cell: (r) => fmtNum(r.source_count) },
              { key: "mir", header: "Mirror", align: "right", cell: (r) => fmtNum(r.mirror_count) },
              { key: "st", header: "Status", cell: (r) => <ToneBadge tone={r.in_sync ? "success" : "warning"}>{r.in_sync ? "In sync" : "Drift"}</ToneBadge> },
            ]}
            card={(r) => (
              <div className="flex items-center justify-between gap-2">
                <span className="min-w-0">
                  <span className="block truncate font-medium text-dt-text-primary">{r.site_id} · epoch {r.source_epoch}</span>
                  <span className="text-xs text-dt-text-secondary">Source {fmtNum(r.source_count)} · Mirror {fmtNum(r.mirror_count)}</span>
                </span>
                <ToneBadge tone={r.in_sync ? "success" : "warning"}>{r.in_sync ? "In sync" : "Drift"}</ToneBadge>
              </div>
            )} />
        )}
      </Panel>

      <Panel title="Recent syncs" subtitle="Scheduled every minute; “Sync now” requests appear as AD_HOC">
        <DataView<SyncRun> caption="Recent syncs" rows={history.data ?? []} rowKey={(r) => r.run_id}
          columns={[
            { key: "req", header: "Requested", cell: (r) => <span className="whitespace-nowrap">{formatDateTime(r.requested_at)}</span> },
            { key: "trig", header: "Trigger", cell: (r) => r.trigger_type },
            { key: "st", header: "Status", cell: (r) => <RunStatus r={r} /> },
            { key: "read", header: "Read", align: "right", cell: (r) => fmtNum(r.events_read) },
            { key: "new", header: "New", align: "right", cell: (r) => fmtNum(r.events_inserted) },
            { key: "old", header: "Already mirrored", align: "right", minWidth: "lg", cell: (r) => fmtNum(r.events_existing) },
          ]}
          card={(r) => (
            <div className="flex items-center justify-between gap-2 text-sm">
              <span className="min-w-0">
                <span className="flex items-center gap-1 text-dt-text-primary"><Clock className="size-3.5" aria-hidden />{formatDateTime(r.requested_at)}</span>
                <span className="text-xs text-dt-text-secondary">{r.trigger_type} · {fmtNum(r.events_inserted)} new of {fmtNum(r.events_read)} read</span>
              </span>
              <RunStatus r={r} />
            </div>
          )} />
      </Panel>
      <p className="flex items-center gap-1 text-xs text-dt-text-secondary"><Radio className="size-3.5" aria-hidden /> This page refreshes every 30 seconds.</p>
    </div>
  );
}

function RunStatus({ r }: { r: SyncRun }) {
  const tone = r.status === "SUCCEEDED" ? "success" : r.status === "FAILED" ? "danger" : "neutral";
  return <span title={r.error_summary ?? undefined}><ToneBadge tone={tone}>{r.status}</ToneBadge></span>;
}

export default function SiteHealthPage() {
  return <AdminOnly permission={PERM.HEALTH}><HealthView /></AdminOnly>;
}
