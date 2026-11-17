"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Clock, Grid3x3, ShieldCheck, Users as UsersIcon } from "lucide-react";
import { ApiError, getAdminDashboard } from "@/lib/api";
import { PageHeader } from "@dijione/design-system";
import { MetricCard } from "@dijione/design-system";
import { LoadingState, ErrorState } from "@dijione/design-system";

// Each attempt is abandoned after this long, then retried. A server error or timeout is
// retried twice; a refusal (4xx) is shown at once. Worst case ≈ 3 × 20 s before the error.
const DASHBOARD_ATTEMPT_TIMEOUT_MS = 20_000;
const DASHBOARD_RETRIES = 2;
// After this long the loading message explains the wait instead of spinning silently.
const DASHBOARD_SLOW_NOTICE_MS = 5_000;

async function loadDashboard(signal: AbortSignal) {
  const attempt = new AbortController();
  const timer = setTimeout(() => attempt.abort(), DASHBOARD_ATTEMPT_TIMEOUT_MS);
  const cancel = () => attempt.abort();
  signal.addEventListener("abort", cancel);
  try {
    return await getAdminDashboard(attempt.signal);
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", cancel);
  }
}

function retryable(failureCount: number, error: unknown) {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < DASHBOARD_RETRIES;
}

function useSlowNotice(active: boolean) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!active) return;
    const timer = setTimeout(() => setSlow(true), DASHBOARD_SLOW_NOTICE_MS);
    return () => {
      clearTimeout(timer);
      setSlow(false);
    };
  }, [active]);
  return active && slow;
}

export default function AdminDashboardPage() {
  const query = useQuery({
    queryKey: ["admin", "dashboard"],
    queryFn: ({ signal }) => loadDashboard(signal),
    retry: retryable,
    retryDelay: 1_000,
  });
  const slow = useSlowNotice(query.isLoading);

  const loadingLabel =
    query.failureCount > 0
      ? "Still waiting for the Admin service — trying again…"
      : slow
        ? "Still loading — the Admin service is taking longer than usual to respond…"
        : "Loading admin dashboard…";

  return (
    <div>
      <PageHeader
        title="Admin Center"
        description="Centralized identity, authorization and module administration for DijiOne."
      />
      {query.isLoading && <LoadingState label={loadingLabel} />}
      {query.isError && (
        <ErrorState
          message={
            query.error instanceof ApiError && query.error.status < 500
              ? `Could not load the admin dashboard: ${query.error.message}`
              : "The admin dashboard did not respond. Check your connection and try again."
          }
          onRetry={() => query.refetch()}
        />
      )}
      {query.data && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <MetricCard label="Total Users" value={query.data.total_users} icon={UsersIcon} tone="brand" />
          <MetricCard label="Active Users" value={query.data.active_users} icon={CheckCircle2} />
          <MetricCard label="Super Admins" value={query.data.super_admins} icon={ShieldCheck} />
          <MetricCard label="Platform Admins" value={query.data.platform_admins} icon={ShieldCheck} />
          <MetricCard label="Active Modules" value={query.data.active_modules} icon={Grid3x3} />
          <MetricCard
            label="Talent Requests Pending Review"
            value={query.data.pending_talent_requests}
            icon={Clock}
          />
        </div>
      )}
    </div>
  );
}
