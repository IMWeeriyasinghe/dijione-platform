"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, EmptyState, ErrorState, LoadingState, PageHeader } from "@dijione/design-system";
import { MapPin } from "lucide-react";
import { ToneBadge } from "@/components/ToneBadge";
import { getFreshness } from "@/lib/api";
import { FEED_LABEL, FEED_TONE, formatDateTime } from "@/lib/format";

export default function OverviewPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["onsite-freshness"],
    queryFn: getFreshness,
    refetchInterval: 60_000,
  });

  if (isLoading) return <LoadingState label="Loading Diji On-site…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div>
      <PageHeader
        title="Diji On-site"
        description="Attendance feed status for enabled sites. Attendance views arrive with Dashboard V1."
      />
      {data.sites.length === 0 ? (
        <EmptyState
          icon={MapPin}
          title="No enabled sites"
          description="An On-site administrator enables sites from Admin → Sites. Sites stay hidden until enabled."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {data.sites.map((site) => (
            <Card key={site.site_id}>
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
                <CardTitle>{site.site_id}</CardTitle>
                <ToneBadge tone={FEED_TONE[site.feed_state]}>{FEED_LABEL[site.feed_state]}</ToneBadge>
              </CardHeader>
              <CardContent className="space-y-1 text-sm text-dt-text-secondary">
                <p>Latest activity received: <span className="text-dt-text-primary">{formatDateTime(site.latest_received_utc)}</span></p>
                <p>Agent heartbeat: <span className="text-dt-text-primary">{formatDateTime(site.agent_heartbeat_utc)}</span></p>
                {site.feed_state !== "FRESH" && (
                  <p className="text-dt-burnt-orange">
                    The feed may be incomplete — &ldquo;No activity recorded&rdquo; is not reliable until it is current.
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <p className="mt-4 text-xs text-dt-text-secondary">Last DijiOne sync: {formatDateTime(data.last_successful_sync_at)}</p>
    </div>
  );
}
