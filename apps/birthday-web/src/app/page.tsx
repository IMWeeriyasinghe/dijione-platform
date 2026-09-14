"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, BadgeCheck, CakeSlice, Clock3, ListOrdered } from "lucide-react";
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

      {/* Actionable attention cards (plan §M / Phase 1.6 §4-§8) — every
          card's count is produced by the exact same repository predicate
          its link's list filter uses, so a number can never point at a
          different result set than what it counts. */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <Link href="/orders?status_filter=PENDING_VERIFICATION" className="block">
          <MetricCard label="Address verification required" value={summary.pending_verification_count} icon={BadgeCheck} tone="brand" />
        </Link>
        <Link href="/orders?verify=overdue" className="block">
          <MetricCard label="Verification overdue" value={summary.verification_overdue_count} icon={Clock3} />
        </Link>
        <Link href="/orders?status_filter=REQUIRES_REVIEW" className="block">
          <MetricCard label="In review" value={summary.requires_review_count} icon={ListOrdered} />
        </Link>
        <Link href="/orders?status_filter=REQUIRES_ATTENTION,ON_HOLD" className="block">
          <MetricCard label="Exceptions" value={summary.exceptions_count} icon={AlertTriangle} />
        </Link>
        <Link href="/orders?acceptance=awaiting" className="block">
          <MetricCard label="Awaiting supplier acceptance" value={summary.acceptance_awaiting_count} icon={CakeSlice} />
        </Link>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Link href="/orders?acceptance=overdue" className="block">
          <MetricCard label="Acceptance overdue" value={summary.acceptance_overdue_count} icon={Clock3} />
        </Link>
        <Link href="/orders?status_filter=ON_HOLD" className="block">
          <MetricCard label="On hold — needs a decision" value={summary.on_hold_count} icon={Clock3} />
        </Link>
        <Link href="/orders?due=today" className="block">
          <MetricCard label="Deliveries today at risk" value={summary.deliveries_today_at_risk_count} icon={AlertTriangle} />
        </Link>
        <Link href="/orders?due=overdue" className="block">
          <MetricCard label="Overdue deliveries" value={summary.overdue_delivery_count} icon={AlertTriangle} />
        </Link>
      </div>

      {/* Split from the old combined "Open issues / unmatched emails" tile
          (Phase 1.6 §5) — that tile linked only to the unmatched-email
          queue, so an open issue count was never actually reachable from
          it. Two honest tiles now, each linking to where its own number
          actually lives. */}
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Link href="/orders?has_open_issue=true" className="block">
          <MetricCard label="Open issues" value={summary.open_issues_count} icon={AlertTriangle} />
        </Link>
        <Link href="/inbound-emails" className="block">
          <MetricCard label="Unmatched supplier email" value={summary.unmatched_emails_count} icon={AlertTriangle} />
        </Link>
      </div>

      {/* Detection & integration health (plan §1.2) */}
      <div className="mt-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Detection health</CardTitle>
            <span
              className={
                "rounded-full px-2.5 py-0.5 text-xs font-medium " +
                (summary.detection_health?.healthy
                  ? "bg-dt-success/10 text-dt-success"
                  : "bg-dt-danger/10 text-dt-danger")
              }
            >
              {summary.detection_health?.healthy ? "Healthy" : "Attention"}
            </span>
          </CardHeader>
          <CardContent className="text-sm text-dt-text-secondary">
            <p>
              Last scan:{" "}
              <span className="text-dt-text-primary">
                {summary.detection_health?.last_scan_at
                  ? new Date(summary.detection_health.last_scan_at).toLocaleString()
                  : "never"}
              </span>{" "}
              ({summary.detection_health?.last_status ?? "—"})
            </p>
            {(summary.detection_health?.consecutive_deferrals ?? 0) > 0 && (
              <p className="mt-1 text-dt-danger">
                {summary.detection_health.consecutive_deferrals} consecutive deferred scan(s) — People source unavailable.
              </p>
            )}
            {summary.detection_health?.stale && (
              <p className="mt-1 text-dt-danger">No successful scan in the last 26 hours.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="mt-4">
        <Link href="/upcoming" className="block">
          <MetricCard label="Upcoming (14 days)" value={summary.upcoming_count} icon={CakeSlice} tone="brand" />
        </Link>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Orders by Status</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-1">
              {Object.entries(summary.by_status)
                .filter(([, count]) => count > 0)
                .map(([status, count]) => (
                  <li key={status}>
                    <Link
                      href={`/orders?status_filter=${status}`}
                      className="-mx-2 flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-sm transition hover:bg-dt-surface-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dt-orange focus-visible:ring-offset-1"
                    >
                      <StatusBadge status={status} />
                      <span className="font-medium text-dt-text-primary">{count}</span>
                    </Link>
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
            <ul className="flex flex-col gap-1">
              {Object.entries(summary.by_lead_time_class).map(([cls, count]) => (
                <li key={cls}>
                  <Link
                    href={`/orders?lead_time_class=${cls}`}
                    className="-mx-2 flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-sm transition hover:bg-dt-surface-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dt-orange focus-visible:ring-offset-1"
                  >
                    <span className="text-dt-text-secondary">{cls.replace(/_/g, " ")}</span>
                    <span className="font-medium text-dt-text-primary">{count}</span>
                  </Link>
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
                  <li key={order.id}>
                    <Link
                      href={`/orders/${order.id}`}
                      className="-mx-2 flex items-center justify-between rounded-lg px-2 py-2.5 text-sm transition hover:bg-dt-surface-warm"
                    >
                      <span className="min-w-0 truncate text-dt-text-primary">
                        {order.employee_name} · {order.birthday_date}
                      </span>
                      <StatusBadge status={order.status} />
                    </Link>
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
