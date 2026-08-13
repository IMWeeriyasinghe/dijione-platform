"use client";

import { useQuery } from "@tanstack/react-query";
import { Briefcase, Building2, Calendar, FileCheck2, ListChecks, Users } from "lucide-react";
import { getTaDashboard } from "@/lib/api";
import { MetricCard } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { RequestCard } from "@/components/talent/RequestCard";
import { PageHeader } from "@dijione/design-system";

export function TaDashboardView() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["ta-dashboard"],
    queryFn: getTaDashboard,
  });

  if (isLoading) return <LoadingState label="Loading operations dashboard…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div>
      <PageHeader
        title="Operations Dashboard"
        description="Cross-client visibility into everything DijiTalentFlow is currently tracking."
      />

      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Clients" value={data.clients} icon={Building2} />
        <MetricCard label="Active Requests" value={data.active_requests} icon={Briefcase} tone="brand" />
        <MetricCard label="Active Applications" value={data.active_applications} icon={ListChecks} />
        <MetricCard label="Available Candidates" value={data.available_candidates} icon={Users} />
        <MetricCard label="Interviews Scheduled" value={data.interviews_scheduled} icon={Calendar} />
        <MetricCard label="Offers in Progress" value={data.offers_in_progress} icon={FileCheck2} />
        <MetricCard label="Pending CS Review" value={data.pending_review_count} icon={ListChecks} tone="brand" />
      </div>

      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
        Needs Attention — Pending Customer Success Review
      </h2>
      {data.attention_requests.length === 0 ? (
        <EmptyState title="Nothing pending review" description="All submitted requests have been triaged." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.attention_requests.map((r) => (
            <RequestCard key={r.id} request={r} showClient />
          ))}
        </div>
      )}
    </div>
  );
}
