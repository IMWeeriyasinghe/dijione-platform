"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Clock, Grid3x3, ShieldCheck, Users as UsersIcon } from "lucide-react";
import { getAdminDashboard } from "@/lib/api";
import { PageHeader } from "@dijione/design-system";
import { MetricCard } from "@dijione/design-system";
import { LoadingState, ErrorState } from "@dijione/design-system";

export default function AdminDashboardPage() {
  const query = useQuery({ queryKey: ["admin", "dashboard"], queryFn: getAdminDashboard });

  return (
    <div>
      <PageHeader
        title="Admin Center"
        description="Centralized identity, authorization and module administration for DijiOne."
      />
      {query.isLoading && <LoadingState label="Loading admin dashboard…" />}
      {query.isError && <ErrorState message="Could not load the admin dashboard." onRetry={() => query.refetch()} />}
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
