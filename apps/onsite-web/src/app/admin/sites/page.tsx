"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, EmptyState, ErrorState, LoadingState, PageHeader, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import { MapPin } from "lucide-react";
import { AdminOnly } from "@/components/AdminOnly";
import { ToneBadge } from "@/components/ToneBadge";
import { getSites, setSiteEnabled } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

function SitesView() {
  const queryClient = useQueryClient();
  const sites = useQuery({ queryKey: ["onsite-sites"], queryFn: getSites, refetchInterval: 60_000 });
  const toggle = useMutation({
    mutationFn: ({ siteId, enabled }: { siteId: string; enabled: boolean }) => setSiteEnabled(siteId, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["onsite-sites"] }),
  });

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
        <Table>
          <Thead>
            <Tr><Th>Site</Th><Th>Name</Th><Th>Time zone</Th><Th>Last seen</Th><Th>Status</Th><Th></Th></Tr>
          </Thead>
          <tbody>
            {sites.data.map((s) => (
              <Tr key={s.site_id}>
                <Td>{s.site_id}</Td>
                <Td>{s.label ?? s.display_name ?? "—"}</Td>
                <Td>{s.time_zone ?? "—"}</Td>
                <Td>{formatDateTime(s.last_seen_at)}</Td>
                <Td><ToneBadge tone={s.enabled ? "success" : "neutral"}>{s.enabled ? "Enabled" : "Disabled"}</ToneBadge></Td>
                <Td>
                  <Button
                    size="sm"
                    variant={s.enabled ? "secondary" : "primary"}
                    loading={toggle.isPending && toggle.variables?.siteId === s.site_id}
                    onClick={() => toggle.mutate({ siteId: s.site_id, enabled: !s.enabled })}
                  >
                    {s.enabled ? "Disable" : "Enable"}
                  </Button>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
      {toggle.isError && <p className="mt-3 text-sm text-dt-danger">The change was not saved. Please try again.</p>}
    </div>
  );
}

export default function SitesPage() {
  return <AdminOnly><SitesView /></AdminOnly>;
}
