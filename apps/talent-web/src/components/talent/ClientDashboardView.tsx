"use client";

import { useQuery } from "@tanstack/react-query";
import { Briefcase, Calendar, FileCheck2, Plus, Users } from "lucide-react";
import Link from "next/link";
import { getClientDashboard } from "@/lib/api";
import { MetricCard } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { RequestCard } from "@/components/talent/RequestCard";
import { PageHeader } from "@dijione/design-system";
import { Button } from "@dijione/design-system";

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
        description="Track visibility into every talent request you've submitted to Dijital Team."
        action={
          <Link href="/requests/new">
            <Button>
              <Plus className="size-4" />
              New Talent Request
            </Button>
          </Link>
        }
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
          description="Submit your first request and Dijital Team's Customer Success team will review it shortly."
          action={
            <Link href="/requests/new">
              <Button size="sm">New Talent Request</Button>
            </Link>
          }
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
