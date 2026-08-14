"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CakeSlice, Clock3, ListOrdered } from "lucide-react";
import Link from "next/link";
import { getDashboardSummary, getUpcoming } from "@/lib/api";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ErrorState,
  LoadingState,
  MetricCard,
  PageHeader,
  StatusBadge,
} from "@dijione/design-system";

export default function DashboardPage() {
  const {
    data: summary,
    isLoading: summaryLoading,
    isError: summaryError,
    refetch: refetchSummary,
  } = useQuery({ queryKey: ["birthday-dashboard"], queryFn: getDashboardSummary });

  const { data: upcoming, isLoading: upcomingLoading } = useQuery({
    queryKey: ["birthday-upcoming", 14],
    queryFn: () => getUpcoming(14),
  });

  if (summaryLoading) return <LoadingState label="Loading dashboard…" />;
  if (summaryError || !summary) return <ErrorState onRetry={() => refetchSummary()} />;

  return (
    <div>
      <PageHeader
        title="DijiBirthday Dashboard"
        description="Operational overview of the cake-ordering workflow."
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Total Orders" value={summary.total_orders} icon={ListOrdered} tone="brand" />
        <MetricCard label="Upcoming (14 days)" value={summary.upcoming_count} icon={CakeSlice} />
        <MetricCard label="Exceptions" value={summary.exceptions_count} icon={AlertTriangle} />
        <MetricCard
          label="Urgent Lead Time"
          value={summary.by_lead_time_class["URGENT"] ?? 0}
          icon={Clock3}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Orders by Status</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2">
              {Object.entries(summary.by_status)
                .filter(([, count]) => count > 0)
                .map(([status, count]) => (
                  <li key={status} className="flex items-center justify-between text-sm">
                    <StatusBadge status={status} />
                    <span className="font-medium text-dt-text-primary">{count}</span>
                  </li>
                ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Orders by Lead Time Class</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2">
              {Object.entries(summary.by_lead_time_class).map(([cls, count]) => (
                <li key={cls} className="flex items-center justify-between text-sm">
                  <span className="text-dt-text-secondary">{cls.replace(/_/g, " ")}</span>
                  <span className="font-medium text-dt-text-primary">{count}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="mt-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Upcoming Birthdays (next 14 days)</CardTitle>
            <Link href="/upcoming" className="text-sm font-medium text-dt-burnt-orange underline underline-offset-2">
              View all
            </Link>
          </CardHeader>
          <CardContent>
            {upcomingLoading ? (
              <LoadingState label="Loading upcoming birthdays…" />
            ) : !upcoming || upcoming.orders.length === 0 ? (
              <p className="text-sm text-dt-text-secondary">No birthdays in the next 14 days.</p>
            ) : (
              <ul className="flex flex-col divide-y divide-dt-border">
                {upcoming.orders.slice(0, 8).map((order) => (
                  <li key={order.id} className="flex items-center justify-between py-2.5 text-sm">
                    <Link href={`/orders/${order.id}`} className="min-w-0 truncate hover:underline">
                      {order.employee_name} · {order.birthday_date}
                    </Link>
                    <StatusBadge status={order.status} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
