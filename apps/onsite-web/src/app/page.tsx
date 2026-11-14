"use client";

import { Suspense, useMemo } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { Activity, AlertTriangle, ChevronRight, Clock, Fingerprint, Radio, Users, UserX } from "lucide-react";
import { BarChart, BreakdownList } from "@/components/charts";
import { PeriodControl, SiteSelect } from "@/components/FilterBar";
import { MappingBadge } from "@/components/FlagChips";
import { ExportButton } from "@/components/ExportButton";
import { FreshnessIndicator } from "@/components/FreshnessIndicator";
import { buttonClass, EmployeeRefCell, InlineAlert, KpiCard, PageTop, Panel, Segmented, Skeleton } from "@/components/kit";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { SyncNowButton } from "@/components/SyncNowButton";
import { EmployeeProfile } from "@/components/EmployeeProfile";
import { HourActivitySheet } from "@/components/HourActivitySheet";
import { getHourly, getOverview, getRecent, getTrend, type Overview } from "@/lib/dashboard";
import { addDays, localTime } from "@/lib/flags";
import { FEED_LABEL } from "@/lib/format";
import { liveQuery } from "@/lib/live-refresh";
import { hasPermission, PERM, useOnsiteScope } from "@/lib/onsite-scope";
import { dayCount, fmtDay, fmtNum, fmtPeriod, fmtShortDay, isSingleDay, type Period, previousPeriod } from "@/lib/period";
import { hrefWith, useUrlState } from "@/lib/url-state";

const HELP = {
  employees: "Distinct verified team members (by BHR Employee ID — several ZKBioTime IDs of one person count once) with at least one recorded activity in the period. Not a measure of presence or absence.",
  events: "Activity events attributed to verified team members in the period. Punches of unmapped ZKBioTime IDs are excluded (see Identity Management).",
  review: "Distinct team members with at least one review flag in the period. A flag is a prompt to look, not a confirmed issue.",
  single: "Distinct team members with a completed day on which only one activity was recorded.",
  unmapped: "ZKBioTime IDs with activity in the period but no verified BambooHR mapping, and their punches. Excluded from attendance figures until an administrator verifies them. Visible to administrators only.",
  feed: "Whether DijiOne's mirror of Diji On-site Attendance is current. Open Site Health for the details.",
};

function OverviewView() {
  const { site } = useSite();
  const { scope } = useOnsiteScope();
  const queryClient = useQueryClient();
  const [s, set] = useUrlState({ from: site.today, to: site.today, trend: "30", hour: "", open: "" });
  // Changing the period always clears an hour selection, so no widget shows a different range.
  const setPeriod = (p: Period) => set({ from: p.from, to: p.to, hour: "" });
  const period: Period = { from: s.from, to: s.to };
  const single = isSingleDay(period);
  const inProgress = period.to >= site.today;
  const rangeParams = single ? { site_id: site.site_id, date: period.from } : { site_id: site.site_id, date_from: period.from, date_to: period.to };
  const prev = previousPeriod(period);
  const prevParams = isSingleDay(prev) ? { site_id: site.site_id, date: prev.from } : { site_id: site.site_id, date_from: prev.from, date_to: prev.to };
  const trendDays = Number(s.trend) === 7 ? 7 : 30;

  const overview = useQuery({ queryKey: ["onsite-overview", rangeParams], queryFn: () => getOverview(rangeParams), ...liveQuery });
  const previous = useQuery({ queryKey: ["onsite-overview", prevParams], queryFn: () => getOverview(prevParams), enabled: !inProgress, ...liveQuery });
  const hourly = useQuery({ queryKey: ["onsite-hourly", rangeParams], queryFn: () => getHourly(rangeParams), ...liveQuery });
  const trend = useQuery({
    queryKey: ["onsite-trend", site.site_id, trendDays, period.to],
    queryFn: () => getTrend({ site_id: site.site_id, days: trendDays, date_to: period.to }),
    ...liveQuery,
  });
  const recent = useQuery({ queryKey: ["onsite-recent", site.site_id], queryFn: () => getRecent({ site_id: site.site_id, limit: 10 }), ...liveQuery });

  const periodLabel = fmtPeriod(period, site.today);
  const cmpLabel = single ? fmtDay(prev.from) : `previous ${dayCount(prev)} days`;
  const delta = (pick: (o: Overview) => number) =>
    !inProgress && overview.data && previous.data ? { value: pick(overview.data), previous: pick(previous.data), label: cmpLabel } : null;
  const ex = (flag?: string) => hrefWith("/exceptions", { from: period.from, to: period.to, flag });

  const hours = useMemo(() => hourly.data?.hours ?? [], [hourly.data]);
  const peak = useMemo(() => {
    const max = Math.max(0, ...hours.map((h) => h.events));
    return new Set(max ? hours.filter((h) => h.events === max).map((h) => String(h.hour)) : []);
  }, [hours]);
  const trendData = trend.data?.days ?? [];
  const active = trendData.filter((d) => d.events > 0);
  const avg = active.length ? Math.round(active.reduce((a, d) => a + d.events, 0) / active.length) : 0;

  if (overview.isLoading) return <OverviewSkeleton />;
  if (!overview.data) return <ErrorState onRetry={() => overview.refetch()} />;
  const o = overview.data;
  const k = o.kpis;
  const feed = k.feed_state ?? "NOT_SYNCED";
  const emptyToday = single && period.from === site.today && k.total_events === 0;

  return (
    <div className="space-y-4">
      <PageTop
        title="Attendance overview"
        description={<>Recorded activity at <span className="font-medium text-dt-text-primary">{site.name}</span>, in site-local time{site.time_zone ? ` (${site.time_zone})` : ""}.</>}
        actions={
          <>
            {single
              ? <ExportButton path="dashboard/overview" params={{ site_id: site.site_id, date: period.from }} label="Export day summary" />
              : <ExportButton path="activity" params={{ site_id: site.site_id, date_from: period.from, date_to: period.to }} label="Export activity" />}
            {hasPermission(scope, PERM.SYNC) && <SyncNowButton onDone={() => queryClient.invalidateQueries()} />}
          </>
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <SiteSelect />
          <PeriodControl value={period} today={site.today} onChange={setPeriod} />
        </div>
        <FreshnessIndicator siteId={site.site_id} queries={[overview, hourly, trend, recent]} />
      </PageTop>

      {single && period.from !== site.today ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-dt-orange/40 bg-dt-cream px-3 py-2 text-sm" role="status">
          <span>Selected day: <span className="font-semibold text-dt-text-primary">{fmtDay(period.from, true)}</span>
            <span className="text-dt-text-secondary"> · every widget below shows this day</span></span>
          <span className="flex flex-wrap gap-2">
            <Link href={hrefWith("/activity", { from: period.from, to: period.from })} className={buttonClass("secondary")}>View all events</Link>
            <button type="button" className={buttonClass("ghost")} onClick={() => setPeriod({ from: site.today, to: site.today })}>Clear selection</button>
          </span>
        </div>
      ) : (
        <p className="text-sm text-dt-text-secondary">
          Showing <span className="font-semibold text-dt-text-primary">{periodLabel}</span>
          {inProgress && <span> · day in progress, figures grow as activity is recorded</span>}
        </p>
      )}

      {emptyToday && (
        <InlineAlert tone="info" action={site.last_activity_date && site.last_activity_date !== site.today ? (
          <button type="button" className={buttonClass("secondary")} onClick={() => setPeriod({ from: site.last_activity_date!, to: site.last_activity_date! })}>
            View {fmtDay(site.last_activity_date)}
          </button>
        ) : undefined}>
          No activity has been recorded yet today (site time). This is not an absence record
          {site.last_activity_date ? <> — the latest recorded activity was on {fmtDay(site.last_activity_date)}.</> : "."}
        </InlineAlert>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 2xl:grid-cols-6">
        <KpiCard label="Team members with activity" value={fmtNum(k.employees_with_activity)} icon={Users} tone="brand" help={HELP.employees}
          delta={delta((x) => x.kpis.employees_with_activity)}
          href={single ? hrefWith("/today", { date: period.from }) : hrefWith("/employees", { from: period.from, to: period.to })}
          hrefLabel={single ? "Open Today" : "Open Team Members"} />
        <KpiCard label="Activity events" value={fmtNum(k.total_events)} icon={Activity} help={HELP.events}
          delta={delta((x) => x.kpis.total_events)}
          sub={!single && k.activity_days ? <span>{fmtNum(k.activity_days)} days with activity</span> : undefined}
          href={hrefWith("/activity", { from: period.from, to: period.to })} hrefLabel="Open Activity" />
        <KpiCard label="Needing review" value={fmtNum(k.employees_needing_review)} icon={AlertTriangle} tone={k.employees_needing_review ? "attention" : "default"}
          help={HELP.review} delta={delta((x) => x.kpis.employees_needing_review)} href={ex()} hrefLabel="Open Exceptions" />
        <KpiCard label="Single activity" value={fmtNum(k.single_punch_employees)} icon={UserX} help={HELP.single}
          delta={delta((x) => x.kpis.single_punch_employees)} href={ex("SINGLE_PUNCH")} />
        {o.operational ? (
          <KpiCard label="Unmapped IDs" value={fmtNum(o.operational.unmapped_codes)} icon={Fingerprint}
            tone={o.operational.unmapped_codes ? "attention" : "default"} help={HELP.unmapped}
            sub={<span>{fmtNum(o.operational.unmapped_punches)} of {fmtNum(o.operational.total_punches)} punches excluded</span>}
            href={hasPermission(scope, PERM.IDENTITY) ? "/admin/identity?tab=unmapped" : undefined} hrefLabel="Open Identity Management" />
        ) : (
          <KpiCard label="Identified team members" value={fmtNum(k.identified_employees ?? k.employees_with_activity)} icon={Fingerprint}
            help={HELP.employees} />
        )}
        <KpiCard label="Feed" value={<span className="text-lg">{FEED_LABEL[feed]}</span>} icon={Radio}
          tone={feed === "FRESH" ? "success" : feed === "DELAYED" ? "attention" : "danger"} help={HELP.feed}
          sub={o.latest_received_utc ? <span>Latest event {new Date(o.latest_received_utc).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span> : undefined}
          href={hasPermission(scope, PERM.HEALTH) ? "/admin/health" : undefined} hrefLabel="Open Site Health" />
      </div>
      {!o.directory_available && (
        <InlineAlert>Team member details are unavailable right now — verified attendance is shown without names.</InlineAlert>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel title="Activity by hour of day" subtitle={`Recorded events per site-local hour · ${periodLabel} · ${site.name}`}
          action={peak.size ? <span className="text-xs text-dt-text-secondary">Busiest: <span className="font-medium text-dt-red">{[...peak].map((h) => `${h.padStart(2, "0")}:00`).join(", ")}</span></span> : undefined}>
          {hourly.data ? (
            <>
              <BarChart measure="events" summary={`Activity events by hour, ${periodLabel}, ${site.name}`} highlight={peak} tickEvery={[6, 3]}
                selected={s.hour || null} onSelect={(h) => set({ hour: h })} minBarPx={18}
                data={hours.map((h) => ({ key: String(h.hour), value: h.events, tick: String(h.hour).padStart(2, "0"),
                  label: `${String(h.hour).padStart(2, "0")}:00–${String(h.hour).padStart(2, "0")}:59${site.time_zone ? ` (${site.time_zone})` : ""}${single ? "" : ", all days"}`,
                  note: `${fmtNum(h.employees)} employees` }))}
                empty={emptyToday ? "No activity recorded yet today." : "No activity recorded in this period."} />
              <p className="mt-2 text-xs text-dt-text-secondary">
                {single ? "Select an hour to see its recorded events." : `Each bar combines that hour across all ${dayCount(period)} days. Select one to see its events.`}
              </p>
            </>
          ) : <Skeleton className="h-44 w-full" />}
        </Panel>
        <Panel title="Daily activity trend"
          subtitle={`Events per day, ${trendDays} days to ${fmtShortDay(period.to)} · ${site.name}${avg ? ` · line = average of days with activity (${fmtNum(avg)})` : ""}`}
          action={<Segmented size="sm" label="Trend range" value={String(trendDays)} onChange={(v) => set({ trend: v })}
            options={[{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }]} />}>
          {trend.data ? (
            <>
              <BarChart measure="events" summary={`Daily activity events, ${trendDays} days to ${period.to}, ${site.name}`}
                selected={single ? period.from : null} onSelect={(d) => setPeriod({ from: d, to: d })} tickEvery={trendDays === 7 ? [1, 1] : [7, 3]}
                average={avg ? { value: avg, label: `avg ${fmtNum(avg)}` } : null}
                data={trendData.map((d) => ({ key: d.date, value: d.events, tick: trendDays === 7 ? fmtDay(d.date).slice(0, 3) : fmtShortDay(d.date),
                  label: fmtDay(d.date, true), note: `${fmtNum(d.employees)} employees${avg && d.events ? ` · ${d.events >= avg ? "+" : "−"}${fmtNum(Math.abs(d.events - avg))} vs average` : ""}` }))} />
              <p className="mt-2 text-xs text-dt-text-secondary">Select a day to view it in this overview.</p>
            </>
          ) : <Skeleton className="h-44 w-full" />}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[2fr_3fr]">
        <Panel title="Needs review" subtitle={`Team-member days per review category · ${periodLabel}. Flags are prompts, not confirmed issues.`}>
          <BreakdownList counts={o.review_breakdown} hrefFor={(f) => ex(f)} />
        </Panel>
        <Panel title="Recent activity" subtitle={`Latest recorded events at ${site.name}`}
          action={<Link href="/activity" className="inline-flex min-h-9 items-center gap-0.5 text-xs font-medium text-dt-burnt-orange">All activity <ChevronRight className="size-3" aria-hidden /></Link>}
          bodyClassName="p-0">
          <div className="flex flex-wrap gap-2 border-b border-dt-border/70 px-4 py-2">
            <Link className="inline-flex min-h-9 items-center rounded-full border border-dt-border px-3 text-xs hover:bg-dt-surface-warm" href={hrefWith("/activity", { from: site.today, to: site.today })}>Today’s activity</Link>
            {hasPermission(scope, PERM.IDENTITY) && (
              <Link className="inline-flex min-h-9 items-center rounded-full border border-dt-border px-3 text-xs hover:bg-dt-surface-warm" href="/admin/identity?tab=unmapped">Unmapped IDs</Link>
            )}
            <Link className="inline-flex min-h-9 items-center rounded-full border border-dt-border px-3 text-xs hover:bg-dt-surface-warm" href={hrefWith("/exceptions", { from: addDays(site.today, -6), to: site.today })}>Review queue (7 days)</Link>
          </div>
          {recent.data && recent.data.items.length > 0 ? (
            <ul className="divide-y divide-dt-border/60">
              {recent.data.items.map((e, i) => (
                <li key={e.event_id ?? `${e.emp_code}-${e.local_time}-${i}`}>
                  <button type="button" onClick={() => set({ open: e.bamboohr_id ?? "" })}
                    className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 text-left hover:bg-dt-surface-warm/60 focus-visible:bg-dt-surface-warm focus-visible:outline-none sm:grid-cols-[minmax(10rem,1fr)_minmax(0,auto)_auto]">
                    <EmployeeRefCell r={e} meta={e.department ?? undefined} size="sm" />
                    <span className="min-w-0 text-right text-sm sm:text-left">
                      <span className="flex items-center justify-end gap-1 tabular-nums text-dt-text-primary sm:justify-start">
                        <Clock className="size-3.5 text-dt-text-secondary" aria-hidden />
                        {e.local_date === site.today ? "Today" : fmtShortDay(e.local_date)} {localTime(e.local_time)}
                      </span>
                      <span className="block truncate text-xs text-dt-text-secondary">{e.terminal ?? "—"}</span>
                    </span>
                    <span className="hidden sm:block"><MappingBadge status={e.mapping_status} cls={e.identity_class} /></span>
                  </button>
                </li>
              ))}
            </ul>
          ) : recent.data ? (
            <p className="px-4 py-6 text-sm text-dt-text-secondary">No activity recorded in the last 92 days.</p>
          ) : <div className="p-4"><Skeleton className="h-40 w-full" /></div>}
        </Panel>
      </div>

      {s.hour !== "" && (
        <HourActivitySheet period={period} hour={Number(s.hour)}
          employees={hours.find((h) => String(h.hour) === s.hour)?.employees ?? null}
          onHour={(h) => set({ hour: String(h) })} onClose={() => set({ hour: "" })} onOpenEmployee={(code) => set({ open: code })} />
      )}
      {s.open && <EmployeeProfile code={s.open} to={period.to} onClose={() => set({ open: "" })} />}
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading attendance overview">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-10 w-full max-w-xl" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 2xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-28" />)}
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2"><Skeleton className="h-64" /><Skeleton className="h-64" /></div>
      <span className="sr-only">Loading attendance overview…</span>
    </div>
  );
}

export default function OverviewPage() {
  return (
    <SiteProvider>
      <Suspense fallback={<OverviewSkeleton />}>
        <OverviewView />
      </Suspense>
    </SiteProvider>
  );
}
