"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ErrorState,
  LoadingState,
  PageHeader,
  Table,
  Td,
  Th,
  Thead,
  Tr,
} from "@dijione/design-system";
import { AdminOnly } from "@/components/AdminOnly";
import { ToneBadge } from "@/components/ToneBadge";
import { getHealth, getSyncHistory } from "@/lib/api";
import { SyncNowButton } from "@/components/SyncNowButton";
import { FEED_LABEL, FEED_TONE, formatDateTime } from "@/lib/format";

function HealthView() {
  const queryClient = useQueryClient();
  const health = useQuery({ queryKey: ["onsite-health"], queryFn: getHealth, refetchInterval: 60_000 });
  const history = useQuery({ queryKey: ["onsite-sync-history"], queryFn: getSyncHistory, refetchInterval: 60_000 });

  if (health.isLoading) return <LoadingState label="Loading site health…" />;
  if (health.isError || !health.data) return <ErrorState onRetry={() => health.refetch()} />;
  const data = health.data;
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["onsite-health"] });
    queryClient.invalidateQueries({ queryKey: ["onsite-sync-history"] });
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Site Health"
        description="Attendance feed, agent heartbeat, DijiOne mirror sync and source reconciliation."
        action={<SyncNowButton onDone={refresh} />}
      />

      <Card>
        <CardHeader><CardTitle>Mirror</CardTitle></CardHeader>
        <CardContent className="space-y-1 text-sm text-dt-text-secondary">
          <p>Last successful sync: <span className="text-dt-text-primary">{formatDateTime(data.last_successful_sync_at)}</span></p>
          <p>
            Latest run: <span className="text-dt-text-primary">{data.latest_run?.status ?? "—"}</span>
            {data.latest_run?.source_unavailable && <span className="ml-2 text-dt-danger">Source unavailable</span>}
            {data.latest_run?.error_summary && <span className="ml-2">({data.latest_run.error_summary})</span>}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Enabled sites</CardTitle></CardHeader>
        <CardContent>
          {data.sites.length === 0 ? (
            <p className="text-sm text-dt-text-secondary">No enabled sites. Enable one from Admin → Sites.</p>
          ) : (
            <Table>
              <Thead>
                <Tr><Th>Site</Th><Th>Feed</Th><Th>Latest received</Th><Th>Agent heartbeat</Th><Th>Pending</Th><Th>Dead-letter</Th><Th>Last error</Th></Tr>
              </Thead>
              <tbody>
                {data.sites.map((s) => (
                  <Tr key={s.site_id}>
                    <Td>{s.site_id}</Td>
                    <Td><ToneBadge tone={FEED_TONE[s.feed_state]}>{FEED_LABEL[s.feed_state]}</ToneBadge></Td>
                    <Td>{formatDateTime(s.latest_received_utc)}</Td>
                    <Td>{formatDateTime(s.agent_heartbeat_utc)}</Td>
                    <Td>{s.agent?.pending_count ?? "—"}</Td>
                    <Td>{s.agent?.dead_letter_count ?? "—"}</Td>
                    <Td>{s.agent?.last_error ?? "—"}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Reconciliation (source vs mirror)</CardTitle></CardHeader>
        <CardContent>
          {data.reconciliation.length === 0 ? (
            <p className="text-sm text-dt-text-secondary">No successful sync yet.</p>
          ) : (
            <Table>
              <Thead>
                <Tr><Th>Site</Th><Th>Epoch</Th><Th>Source</Th><Th>Mirror</Th><Th>Status</Th></Tr>
              </Thead>
              <tbody>
                {data.reconciliation.map((r) => (
                  <Tr key={`${r.site_id}-${r.source_epoch}`}>
                    <Td>{r.site_id}</Td>
                    <Td>{r.source_epoch}</Td>
                    <Td>{r.source_count.toLocaleString()}</Td>
                    <Td>{r.mirror_count.toLocaleString()}</Td>
                    <Td><ToneBadge tone={r.in_sync ? "success" : "warning"}>{r.in_sync ? "In sync" : "Drift"}</ToneBadge></Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Recent syncs</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <Thead>
              <Tr><Th>Requested</Th><Th>Trigger</Th><Th>Status</Th><Th>Read</Th><Th>New</Th><Th>Already mirrored</Th></Tr>
            </Thead>
            <tbody>
              {(history.data ?? []).map((r) => (
                <Tr key={r.run_id}>
                  <Td>{formatDateTime(r.requested_at)}</Td>
                  <Td>{r.trigger_type}</Td>
                  <Td>{r.status}</Td>
                  <Td>{r.events_read.toLocaleString()}</Td>
                  <Td>{r.events_inserted.toLocaleString()}</Td>
                  <Td>{r.events_existing.toLocaleString()}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

export default function SiteHealthPage() {
  return <AdminOnly><HealthView /></AdminOnly>;
}
