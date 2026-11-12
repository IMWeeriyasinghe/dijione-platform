"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, EmptyState, LoadingState, MetricCard, PageHeader, StatusBadge } from "@dijione/design-system";
import { AlertTriangle, CheckCircle2, ClipboardCheck, Coffee, Users } from "lucide-react";
import { OfflineBanner, Page, QueryError, RequirePermission } from "@/components/ui";
import { management, type LiveEmployee } from "@/lib/api";
import { longDate, shortDuration, time, WORK_MODE_LABEL } from "@/lib/format";
import { hasPermission, PERM, useAtworkScope } from "@/lib/atwork-scope";
import { useDisplay } from "@/lib/hooks";

function People({ title, people, zone, empty }: { title: string; people: LiveEmployee[]; zone: string; empty: string }) {
  const { format } = useDisplay();
  return (
    <Card className="p-5">
      <h2 className="text-base font-semibold">{title}</h2>
      {people.length === 0 ? <p className="mt-3 text-sm text-dt-text-secondary">{empty}</p> : (
        <ul className="mt-3 divide-y divide-dt-border text-sm">
          {people.map((p) => (
            <li key={p.session.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <Link href={`/management/employees/${p.platform_user_id}`} className="font-medium underline-offset-2 hover:underline">{p.employee_name}</Link>
              <span className="flex items-center gap-2 text-dt-text-secondary">{WORK_MODE_LABEL[p.session.work_mode]} · since {time(p.session.check_in_at, zone, format)}{p.overdue && <StatusBadge status="REQUIRES_ATTENTION" label="Overdue" />}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Screen() {
  const { scope } = useAtworkScope();
  const { format } = useDisplay();
  const can = hasPermission(scope, PERM.READ_ALL);
  const query = useQuery({ queryKey: ["atwork", "overview"], queryFn: management.overview, enabled: can, refetchInterval: 60_000, refetchOnWindowFocus: "always" });
  if (!can) return <><PageHeader title="Management" /><EmptyState title="No overview available" description="Your role does not include organization-wide attendance. Use the other Management sections available to you." /></>;
  if (query.isLoading) return <LoadingState />;
  if (!query.data) return <QueryError error={query.error} retry={() => query.refetch()} />;
  const d = query.data;
  return (
    <>
      <PageHeader title="Management Overview" description={`${longDate(d.date)} · ${d.time_zone}`} />
      <OfflineBanner />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Working now" value={d.working_count} icon={Users} tone="brand" />
        <MetricCard label="On break" value={d.on_break_count} icon={Coffee} />
        <MetricCard label="Completed today" value={d.completed_today} icon={CheckCircle2} />
        {d.pending_corrections !== null ? <MetricCard label="Pending corrections" value={d.pending_corrections} icon={ClipboardCheck} href="/management/corrections" /> : <MetricCard label="Exceptions" value={d.exception_count} icon={AlertTriangle} />}
      </div>
      <p className="mt-4 text-sm text-dt-text-secondary">Today so far: gross {shortDuration(d.totals.gross_seconds)} · break {shortDuration(d.totals.break_seconds)} · net {shortDuration(d.totals.net_seconds)}{(d.totals.provisional_seconds ?? 0) > 0 && <span className="text-dt-warning"> · unverified {shortDuration(d.totals.provisional_seconds ?? 0)}, not included</span>}</p>
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <People title="Currently working" people={d.working} zone={d.time_zone} empty="Nobody is checked in right now." />
        <People title="On break" people={d.on_break} zone={d.time_zone} empty="Nobody is on a break right now." />
        <Card className="p-5">
          <h2 className="text-base font-semibold">Attendance exceptions</h2>
          {d.exceptions.length === 0 ? <p className="mt-3 text-sm text-dt-text-secondary">No sessions are past the missed check-out threshold.</p> : (
            <ul className="mt-3 divide-y divide-dt-border text-sm">
              {d.exceptions.map((e) => <li key={e.session_id} className="flex flex-wrap justify-between gap-2 py-2"><Link href={`/management/employees/${e.platform_user_id}`} className="font-medium underline-offset-2 hover:underline">{e.employee_name}</Link><span className="text-dt-text-secondary">Open {shortDuration(e.open_seconds)}{e.break_open ? " · break still open" : ""}</span></li>)}
            </ul>
          )}
        </Card>
        <Card className="p-5">
          <h2 className="text-base font-semibold">Completed sessions today</h2>
          {d.completed.length === 0 ? <p className="mt-3 text-sm text-dt-text-secondary">None yet today.</p> : (
            <ul className="mt-3 divide-y divide-dt-border text-sm">
              {d.completed.map((c) => <li key={c.session.id} className="flex flex-wrap justify-between gap-2 py-2"><Link href={`/management/employees/${c.platform_user_id}`} className="font-medium underline-offset-2 hover:underline">{c.employee_name}</Link><span className="text-dt-text-secondary">{time(c.session.check_in_at, d.time_zone, format)}–{c.session.check_out_at && time(c.session.check_out_at, d.time_zone, format)} · net {shortDuration(c.session.totals.net_seconds)}</span></li>)}
            </ul>
          )}
        </Card>
      </div>
      <Card className="mt-4 p-5">
        <h2 className="text-base font-semibold">Access</h2>
        <p className="mt-1 text-sm text-dt-text-secondary">Employee access is automatic. Manager access is granted by DijiOne administrators, individually or through an Access Group.</p>
        <a className="mt-2 inline-block text-sm font-medium text-dt-burnt-orange underline underline-offset-2" href="/admin/applications/atwork">Open DijiOne Admin Center</a>
      </Card>
    </>
  );
}

export default function ManagementPage() {
  const { scope } = useAtworkScope();
  if (!hasPermission(scope, PERM.MANAGEMENT)) {
    return <EmptyState title="Management access required" description="This area is limited to DijiAtWork managers." />;
  }
  return <Page><RequirePermission permission={PERM.MANAGEMENT} title="Management access required"><Screen /></RequirePermission></Page>;
}
