"use client";

import { Briefcase, CalendarClock, Users } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ErrorState, LoadingState, MetricCard, StatusBadge } from "@dijione/design-system";

import { getDashboard } from "@/lib/api";

export default function OverviewPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["external-dashboard"],
    queryFn: getDashboard,
  });

  if (isLoading) return <LoadingState label="Loading your workspace…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-dt-text-primary">Overview</h2>
        <p className="text-sm text-dt-text-secondary">
          Where your talent requests stand right now.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Active requests" value={data.active_requests} icon={Briefcase} tone="brand" />
        <MetricCard label="Candidates in process" value={data.candidates_in_process} icon={Users} />
        <MetricCard label="Interviews this week" value={data.interviews_this_week} icon={CalendarClock} />
        <MetricCard label="Offers in progress" value={data.offers_in_progress} icon={Briefcase} />
      </div>

      <div className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-dt-text-primary">Your requests</h3>
          <Link
            href="/requests"
            className="text-sm font-medium text-dt-burnt-orange underline underline-offset-2"
          >
            View all →
          </Link>
        </div>
        {data.requests.length === 0 ? (
          <p className="text-sm text-dt-text-secondary">No active requests yet.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {data.requests.slice(0, 5).map((r) => (
              <li key={r.id}>
                <Link
                  href={`/requests/${r.id}`}
                  className="block rounded-xl border border-dt-border bg-dt-surface p-4 hover:border-dt-orange"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium text-dt-text-primary">{r.designation}</span>
                    <StatusBadge status={r.current_stage} />
                  </div>
                  <p className="mt-1 text-sm text-dt-text-secondary">{r.client_safe_status_text}</p>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-dt-cream">
                    <div
                      className="h-full rounded-full bg-dt-orange"
                      style={{ width: `${Math.min(100, Math.max(0, r.progress_percent))}%` }}
                    />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
