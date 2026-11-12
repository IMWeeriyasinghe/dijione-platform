"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, EmptyState, ErrorState, LoadingState, PageHeader } from "@dijione/design-system";
import { DataView } from "@/components/DataView";
import type { OnsiteSite } from "@/lib/types";
import { MapPin } from "lucide-react";
import { AdminOnly } from "@/components/AdminOnly";
import { PERM } from "@/lib/onsite-scope";
import { ToneBadge } from "@/components/ToneBadge";
import { getSites, setSiteEnabled } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

function SitesView() {
  const queryClient = useQueryClient();
  const sites = useQuery({ queryKey: ["onsite-sites"], queryFn: getSites, refetchInterval: 60_000 });
  const toggle = useMutation({
    mutationFn: ({ siteId, enabled }: { siteId: string; enabled: boolean }) => setSiteEnabled(siteId, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["onsite-sites"] });
      queryClient.invalidateQueries({ queryKey: ["onsite-sites-info"] });
    },
  });

  const toggleButton = (s: OnsiteSite) => (
    <Button size="sm" variant={s.enabled ? "secondary" : "primary"} loading={toggle.isPending && toggle.variables?.siteId === s.site_id}
      onClick={() => toggle.mutate({ siteId: s.site_id, enabled: !s.enabled })}>
      {s.enabled ? "Disable" : "Enable"}
    </Button>
  );

  if (sites.isLoading) return <LoadingState label="Loading sites…" />;
  if (sites.isError || !sites.data) return <ErrorState onRetry={() => sites.refetch()} />;

  return (
    <div>
      <PageHeader
        title="Sites"
        description="Sites are discovered from the attendance source and stay disabled until enabled here. Disabled sites are invisible everywhere else."
      />
      {sites.data.length === 0 ? (
        <EmptyState icon={MapPin} title="No sites discovered yet" description="Run a sync from Site Health to discover sites." />
      ) : (
        <DataView<OnsiteSite> caption="Discovered sites" rows={sites.data} rowKey={(s) => s.site_id}
          columns={[
            { key: "site", header: "Site", cell: (s) => <span className="font-mono text-xs">{s.site_id}</span> },
            { key: "name", header: "Name", cell: (s) => s.label ?? s.display_name ?? "—" },
            { key: "tz", header: "Time zone", minWidth: "lg", cell: (s) => s.time_zone ?? "—" },
            { key: "seen", header: "Last seen", minWidth: "lg", cell: (s) => formatDateTime(s.last_seen_at) },
            { key: "status", header: "Status", cell: (s) => <ToneBadge tone={s.enabled ? "success" : "neutral"}>{s.enabled ? "Enabled" : "Disabled"}</ToneBadge> },
            { key: "action", header: <span className="sr-only">Action</span>, align: "right", cell: (s) => toggleButton(s) },
          ]}
          card={(s) => (
            <div className="space-y-2">
              <div className="flex items-start justify-between gap-2">
                <span className="min-w-0">
                  <span className="block font-medium text-dt-text-primary">{s.label ?? s.display_name ?? s.site_id}</span>
                  <span className="block truncate font-mono text-xs text-dt-text-secondary">{s.site_id}</span>
                </span>
                <ToneBadge tone={s.enabled ? "success" : "neutral"}>{s.enabled ? "Enabled" : "Disabled"}</ToneBadge>
              </div>
              <p className="text-xs text-dt-text-secondary">{s.time_zone ?? "—"} · last seen {formatDateTime(s.last_seen_at)}</p>
              {toggleButton(s)}
            </div>
          )} />
      )}
      {toggle.isError && <p className="mt-3 text-sm text-dt-danger">The change was not saved. Please try again.</p>}
    </div>
  );
}

export default function SitesPage() {
  return <AdminOnly permission={PERM.SITES}><SitesView /></AdminOnly>;
}
