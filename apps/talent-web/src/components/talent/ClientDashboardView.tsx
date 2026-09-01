"use client";

import { useQuery } from "@tanstack/react-query";
import { Briefcase, Calendar, FileCheck2, Users } from "lucide-react";
import { getClientDashboard } from "@/lib/api";
import { MetricCard } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { RequestCard } from "@/components/talent/RequestCard";
import { PageHeader } from "@dijione/design-system";

export function ClientDashboardView() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["client-dashboard"],
    queryFn: getClientDashboard,
  });

  if (isLoading) return <LoadingState label="Loading your dashboard…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Track visibility into every talent request Dijital Team is working on for you."
      />

      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Active Requests" value={data.active_requests} icon={Briefcase} tone="brand" />
        <MetricCard label="Candidates in Process" value={data.candidates_in_process} icon={Users} />
        <MetricCard label="Interviews This Week" value={data.interviews_this_week} icon={Calendar} />
        <MetricCard label="Offers in Progress" value={data.offers_in_progress} icon={FileCheck2} />
      </div>

      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
        Your Talent Requests
      </h2>
      {data.requests.length === 0 ? (
        <EmptyState
          title="No talent requests yet"
          description="Dijital Team's Talent Acquisition team will get in touch when there's a request to track here."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.requests.map((r) => (
            <RequestCard key={r.id} request={r} />
          ))}
        </div>
      )}
    </div>
  );
}
