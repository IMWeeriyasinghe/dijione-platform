"use client";

import { useQuery } from "@tanstack/react-query";
import { Briefcase, Building2, Calendar, FileCheck2, ListChecks } from "lucide-react";
import { getTaDashboard } from "@/lib/api";
import { MetricCard } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { RequestCard } from "@/components/talent/RequestCard";
import { RecruitmentSyncStatus } from "@/components/talent/RecruitmentSyncStatus";
import { PageHeader } from "@dijione/design-system";
import Link from "next/link";

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

      <RecruitmentSyncStatus />

      {/* "Available Candidates" (availability_status==AVAILABLE) is
          intentionally not shown — that field has no real source and is
          structurally 0 against Lever-promoted data (plan §D). */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Clients" value={data.clients} icon={Building2} href="/clients" />
        <MetricCard
          label="Active Requests"
          value={data.active_requests}
          icon={Briefcase}
          tone="brand"
          href="/requests?status=active"
        />
        <MetricCard
          label="Active Applications"
          value={data.active_applications}
          icon={ListChecks}
          href="/applications"
        />
        <MetricCard
          label="Interviews Scheduled"
          value={data.interviews_scheduled}
          icon={Calendar}
          href={data.interviews_scheduled > 0 ? "/interviews" : undefined}
        />
        <MetricCard
          label="Offers in Progress"
          value={data.offers_in_progress}
          icon={FileCheck2}
          href={data.offers_in_progress > 0 ? "/applications?status=OFFER" : undefined}
        />
      </div>

      <div className="mb-8 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
          Needs Attention — Pending Customer Success Review
        </h2>
        {/* Demoted out of the primary metric grid (plan §D) — structurally
            0 for Lever-promoted requests today; kept as a small, still-
            clickable count for the day a client-submitted request path
            returns. */}
        {data.pending_review_count > 0 ? (
          <Link href="/requests" className="text-xs font-medium text-dt-burnt-orange underline underline-offset-2">
            {data.pending_review_count} pending →
          </Link>
        ) : (
          <span className="text-xs text-dt-text-secondary">{data.pending_review_count} pending</span>
        )}
      </div>
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
