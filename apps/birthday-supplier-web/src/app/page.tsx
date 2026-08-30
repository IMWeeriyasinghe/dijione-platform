"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarClock, CalendarDays, CheckCircle2, PackageCheck, TriangleAlert, Truck } from "lucide-react";
import Link from "next/link";
import {
  Card,
  ErrorState,
  LoadingState,
  MetricCard,
} from "@dijione/design-system";
import { getPortalDashboard } from "@/lib/api";
import { useSupplierAuth } from "@/lib/supplier-auth";

// Fulfilment-only, supplier-scoped dashboard (semi-automation future-state
// plan §N) — deliberately does not mirror the internal dashboard. This
// answers what a supplier actually cares about: what needs acknowledging,
// what's due, what's late, what's open. Nothing here shows another
// supplier's data — every count is server-scoped to this token's supplier.
export default function SupplierDashboardPage() {
  const { token } = useSupplierAuth();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["portal-dashboard"],
    queryFn: () => getPortalDashboard(token!),
    enabled: !!token,
  });

  if (isLoading) return <LoadingState label="Loading dashboard…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-dt-text-primary">Dashboard</h2>
        <p className="text-sm text-dt-text-secondary">Today's fulfilment work, at a glance.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Link href="/orders" className="block">
          <MetricCard label="New orders to accept" value={data.new_orders} icon={CheckCircle2} tone="brand" />
        </Link>
        <Link href="/orders" className="block">
          <MetricCard label="Due today" value={data.due_today} icon={CalendarClock} />
        </Link>
        <Link href="/orders" className="block">
          <MetricCard label="Due tomorrow" value={data.due_tomorrow} icon={CalendarDays} />
        </Link>
        <Link href="/orders" className="block">
          <MetricCard label="Overdue" value={data.overdue} icon={AlertTriangle} />
        </Link>
        <Link href="/orders" className="block">
          <MetricCard label="Out for delivery" value={data.out_for_delivery} icon={Truck} />
        </Link>
        <Link href="/orders" className="block">
          <MetricCard label="Open problems" value={data.open_issues} icon={TriangleAlert} />
        </Link>
      </div>

      <div className="mt-6">
        <Card className="p-5">
          <div className="flex items-center gap-3">
            <PackageCheck className="size-5 text-dt-burnt-orange" />
            <div>
              <p className="text-sm text-dt-text-secondary">Completed today</p>
              <p className="text-2xl font-semibold text-dt-text-primary">{data.completed_today}</p>
            </div>
          </div>
        </Card>
      </div>

      <div className="mt-6 text-sm">
        <Link href="/orders" className="font-medium text-dt-burnt-orange underline underline-offset-2">
          View all orders →
        </Link>
      </div>
    </div>
  );
}
