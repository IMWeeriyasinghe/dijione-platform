"use client";

import { Suspense, useMemo } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { Activity, AlertTriangle, ChevronRight, Clock, Fingerprint, Radio, Users, UserX } from "lucide-react";
import { BreakdownList, seriesValue, StatusBarChart, type StatusBar, type StatusSeries } from "@/components/charts";
import { PeriodControl, SiteSelect } from "@/components/FilterBar";
import { MappingBadge } from "@/components/FlagChips";
import { ExportReportButton } from "@/components/ReportExportDialog";
import { FreshnessIndicator } from "@/components/FreshnessIndicator";
import { buttonClass, EmployeeRefCell, InfoTip, InlineAlert, KpiCard, PageTop, Panel, Segmented, Skeleton } from "@/components/kit";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { SyncNowButton } from "@/components/SyncNowButton";
import { EmployeeProfile } from "@/components/EmployeeProfile";
import { HourActivitySheet } from "@/components/HourActivitySheet";
import { getHourly, getOverview, getRecent, getTrend, type ExtremeBlock, type HourBucket, type Overview } from "@/lib/dashboard";
import { addDays, localTime } from "@/lib/flags";
import { FEED_LABEL, MAPPING_STATE } from "@/lib/format";
import { liveQuery } from "@/lib/live-refresh";
import { hasPermission, PERM, useOnsiteScope } from "@/lib/onsite-scope";
import { dayCount, fmtDay, fmtNum, fmtPeriod, fmtShortDay, isSingleDay, type Period, previousPeriod } from "@/lib/period";
import { hrefWith, useUrlState } from "@/lib/url-state";

const HELP = {
  employees: "Distinct verified team members (by BHR ID — several ZKBioTime IDs of one person count once) with at least one recorded activity in the period. Not a measure of presence or absence.",
  events: "Every attendance event recorded in the period, whatever its mapping status. Verified events are attributed to a team member; unmapped and conflicting events are shown by ZKBioTime ID only. Verified + needs review = recorded.",
  review: "Distinct verified team members with at least one review flag in the period. A flag is a prompt to look, not a confirmed issue.",
  single: "Distinct verified team members with a completed day on which only one fingerprint was recorded. A neutral observation for optional review — not a violation.",
  extreme: "Earliest / latest recorded fingerprint of the site-local day over all recorded fingerprints (every mapping status), at the entry-side reader — not a confirmed presence or exit.",
  unmapped: "ZKBioTime IDs with activity in the period but no verified BambooHR mapping, and their punches. Shown in Activity by ID only; not attributed to anyone until an administrator verifies them.",
  feed: "Whether DijiOne's mirror of Diji On-site Attendance is current. Open Site Health for the details.",
};

const SERIES = [
  { value: "all", label: "All recorded" },
  { value: "verified", label: "Verified" },
  { value: "unverified", label: "Needs review" },
] as const;
const SERIES_NOUN: Record<StatusSeries, string> = { all: "recorded", verified: "verified", unverified: "needs-review" };

/** "first 3 · last 1 · single 2" for the shown series (whole-day first / last recorded punches). */
function sequenceNote(h: HourBucket, series: StatusSeries): string | null {
  const pick = (x?: { verified: number; unmapped: number; conflict: number }) =>
    !x ? 0 : series === "verified" ? x.verified : series === "unverified" ? x.unmapped + x.conflict : x.verified + x.unmapped + x.conflict;
  const first = pick(h.first), last = pick(h.last), single = pick(h.single);
  if (!first && !last && !single) return null;
  return `First recorded fingerprint of the day: ${fmtNum(first)} · last: ${fmtNum(last)} · single: ${fmtNum(single)}`;
}

/** Earliest / Latest Recorded Fingerprint (single site-local day, all mapping states, ties). */
function ExtremeCard({ kind, block, single, today, hrefFor }: {
  kind: "earliest" | "latest"; block: ExtremeBlock | null | undefined; single: boolean; today: boolean;
  hrefFor: (mapping: string, extra?: Record<string, string>) => string;
}) {
  const label = kind === "earliest" ? "Earliest Recorded Fingerprint" : "Latest Recorded Fingerprint";
  if (!single) {
    return <KpiCard label={label} value={<span className="text-base text-dt-text-secondary">Select a single day</span>} icon={Clock} help={HELP.extreme} />;
  }
  if (!block) {
    return <KpiCard label={label} value={<span className="text-base text-dt-text-secondary">None recorded</span>} icon={Clock} help={HELP.extreme} />;
  }
  const e = block.entries[0];
  const verified = e.mapping_state === "VERIFIED";
  const who = verified ? e.employee_name ?? `BHR ID ${e.bamboohr_id}` : `ZKBioTime ID ${e.zk_emp_code}`;
  return (
    <KpiCard label={label} value={localTime(block.local_time)} icon={Clock} help={HELP.extreme}
      sub={<span className="block">
        <span className={MAPPING_STATE[e.mapping_state].text}>{who}</span>
        {block.tied > 1 && <span> · +{block.tied - 1} tied</span>}
        {today && <span className="block text-xs">May change as fingerprints are recorded</span>}
      </span>}
      href={hrefFor(verified ? "verified" : "all", { view: "events", ...(verified ? { q: e.bamboohr_id ?? "" } : { emp: e.zk_emp_code }) })}
      hrefLabel="Open in Activity" />
  );
}

function OverviewView() {
  const { site } = useSite();
  const { scope } = useOnsiteScope();
  const queryClient = useQueryClient();
  const [s, set] = useUrlState({ from: site.today, to: site.today, trend: "30", hour: "", open: "", series: "all" });
  const series = (SERIES.some((x) => x.value === s.series) ? s.series : "all") as StatusSeries;
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
  const hourBars: StatusBar[] = hours.map((h) => {
    const hh = String(h.hour).padStart(2, "0");
    const note = sequenceNote(h, series);
    return { key: String(h.hour), tick: hh, verified: h.verified_events ?? h.events, unmapped: h.unmapped_events ?? 0,
      conflict: h.conflict_events ?? 0,
      label: `${hh}:00–${hh}:59${site.time_zone ? ` (${site.time_zone})` : ""}${single ? "" : ", all days"}`,
      notes: [`${fmtNum(h.employees)} verified team members`, ...(note ? [note] : [])] };
  });
  const peakMax = Math.max(0, ...hourBars.map((b) => seriesValue(b, series)));
  const peak = new Set(peakMax ? hourBars.filter((b) => seriesValue(b, series) === peakMax).map((b) => b.key) : []);
  const trendData = trend.data?.days ?? [];
  const trendBars: StatusBar[] = trendData.map((d) => ({ key: d.date, label: fmtDay(d.date, true),
    tick: trendDays === 7 ? fmtDay(d.date).slice(0, 3) : fmtShortDay(d.date),
    verified: d.verified_events ?? d.events, unmapped: d.unmapped_events ?? 0, conflict: d.conflict_events ?? 0,
    notes: [`${fmtNum(d.employees)} verified team members`] }));
  // The average describes exactly the series shown: days with any shown activity.
  const shownDays = trendBars.map((b) => seriesValue(b, series)).filter((v) => v > 0);
  const avg = shownDays.length ? Math.round(shownDays.reduce((a, v) => a + v, 0) / shownDays.length) : 0;

  if (overview.isLoading) return <OverviewSkeleton />;
  if (!overview.data) return <ErrorState onRetry={() => overview.refetch()} />;
  const o = overview.data;
  const k = o.kpis;
  const feed = k.feed_state ?? "NOT_SYNCED";
  const recorded = k.recorded_events ?? k.total_events;
  const needsReview = (k.unmapped_events ?? 0) + (k.conflict_events ?? 0);
  const emptyToday = single && period.from === site.today && recorded === 0;
  const activityHref = (mapping: string, extra: Record<string, string> = {}) =>
    hrefWith("/activity", { from: period.from, to: period.to, mapping, ...extra });

  return (
    <div className="space-y-4">
      <PageTop
        title="Attendance overview"
        description={<>Recorded activity at <span className="font-medium text-dt-text-primary">{site.name}</span>, in site-local time{site.time_zone ? ` (${site.time_zone})` : ""}.</>}
        actions={
          <>
            <ExportReportButton terminals={site.terminals} departments={site.departments ?? []} context={{
              report: single ? "overview" : "daily", siteId: site.site_id, today: site.today, from: period.from, to: period.to,
              mapping: series }} />
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
            <Link href={hrefWith("/activity", { view: "events", from: period.from, to: period.from, mapping: series })} className={buttonClass("secondary")}>View all events</Link>
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

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
        <KpiCard label="Team members with activity" value={fmtNum(k.employees_with_activity)} icon={Users} tone="brand" help={HELP.employees}
          delta={delta((x) => x.kpis.employees_with_activity)}
          href={single ? hrefWith("/today", { date: period.from }) : hrefWith("/employees", { from: period.from, to: period.to })}
          hrefLabel={single ? "Open Today" : "Open Team Members"} />
        <KpiCard label="Recorded events" value={fmtNum(recorded)} icon={Activity} help={HELP.events}
          delta={delta((x) => x.kpis.recorded_events ?? x.kpis.total_events)}
          sub={k.recorded_events !== undefined ? (
            <span>
              <span className={MAPPING_STATE.VERIFIED.text}>{fmtNum(k.verified_events ?? 0)} verified</span>
              {" · "}<span className={MAPPING_STATE.UNMAPPED.text}>{fmtNum(needsReview)} needs review</span>
              {k.conflict_events ? <> ({fmtNum(k.conflict_events)} conflict)</> : null}
            </span>
          ) : undefined}
          href={activityHref("all")} hrefLabel="Open Activity" />
        <KpiCard label="Needing review" value={fmtNum(k.employees_needing_review)} icon={AlertTriangle} tone={k.employees_needing_review ? "attention" : "default"}
          help={HELP.review} delta={delta((x) => x.kpis.employees_needing_review)} href={ex()} hrefLabel="Open Exceptions" />
        <KpiCard label="Single Recorded Fingerprint" value={fmtNum(k.single_punch_employees)} icon={UserX} help={HELP.single}
          delta={delta((x) => x.kpis.single_punch_employees)} href={ex("SINGLE_PUNCH")} />
        <ExtremeCard kind="earliest" block={o.extremes?.earliest} single={single} today={period.from === site.today} hrefFor={activityHref} />
        <ExtremeCard kind="latest" block={o.extremes?.latest} single={single} today={period.from === site.today} hrefFor={activityHref} />
        {o.operational ? (
          <KpiCard label="Unmapped IDs" value={fmtNum(o.operational.unmapped_codes)} icon={Fingerprint}
            tone={o.operational.unmapped_codes ? "attention" : "default"} help={HELP.unmapped}
            sub={<span>{fmtNum(o.operational.unmapped_punches)} of {fmtNum(o.operational.total_punches)} punches unmapped</span>}
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

      <div className="flex flex-wrap items-center gap-2">
        <Segmented size="sm" label="Chart activity" value={series} onChange={(v) => set({ series: v, hour: "" })}
          options={SERIES.map((x) => ({ value: x.value, label: x.label }))} />
        <InfoTip label="About the activity charts" text="Bars are stacked by identity status for each fingerprint's own site-local day: teal solid = verified, amber dotted = unmapped (needs review), burgundy hatched = mapping conflict. Bar height is the fingerprints shown. Tooltips add the hours of each team member's or ZKBioTime ID's first and last recorded fingerprint of the whole day — recorded order at the entry-side reader, not a confirmed exit." />
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel title="Activity by hour of day" subtitle={`${SERIES.find((x) => x.value === series)!.label} events per site-local hour · ${periodLabel} · ${site.name}`}
          action={peak.size ? <span className="text-xs text-dt-text-secondary">Busiest: <span className="font-medium text-dt-red">{[...peak].map((h) => `${h.padStart(2, "0")}:00`).join(", ")}</span></span> : undefined}>
          {hourly.data ? (
            <>
              <StatusBarChart series={series} summary={`${SERIES.find((x) => x.value === series)!.label} events by hour, ${periodLabel}, ${site.name}`}
                highlight={peak} tickEvery={[6, 3]} selected={s.hour || null} onSelect={(h) => set({ hour: h })} minBarPx={18} data={hourBars}
                empty={emptyToday ? "No activity recorded yet today." : "No activity recorded in this period."} />
              <p className="mt-2 text-xs text-dt-text-secondary">
                {single ? "Select an hour to see its recorded events." : `Each bar combines that hour across all ${dayCount(period)} days. Select one to see its events.`}
              </p>
            </>
          ) : <Skeleton className="h-44 w-full" />}
        </Panel>
        <Panel title="Daily activity trend"
          subtitle={`${SERIES.find((x) => x.value === series)!.label} events per day, ${trendDays} days to ${fmtShortDay(period.to)} · ${site.name}${avg ? ` · dashed line = average ${SERIES_NOUN[series]} events per day with activity (${fmtNum(avg)})` : ""}`}
          action={<Segmented size="sm" label="Trend range" value={String(trendDays)} onChange={(v) => set({ trend: v })}
            options={[{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }]} />}>
          {trend.data ? (
            <>
              <StatusBarChart series={series} summary={`Daily ${SERIES_NOUN[series]} events, ${trendDays} days to ${period.to}, ${site.name}`}
                selected={single ? period.from : null} onSelect={(d) => setPeriod({ from: d, to: d })} tickEvery={trendDays === 7 ? [1, 1] : [7, 3]}
                average={avg ? { value: avg, label: `avg ${fmtNum(avg)} ${SERIES_NOUN[series]}/day` } : null} data={trendBars} />
              <p className="mt-2 text-xs text-dt-text-secondary">
                Select a day to view it in this overview, or <Link className="font-medium text-dt-burnt-orange underline-offset-2 hover:underline"
                  href={hrefWith("/activity", { from: addDays(period.to, -(trendDays - 1)), to: period.to, mapping: series })}>open these {trendDays} days in Activity</Link>.
              </p>
            </>
          ) : <Skeleton className="h-44 w-full" />}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[2fr_3fr]">
        <Panel title="Needs review" subtitle={`Team-member days per review category · ${periodLabel}. Flags are prompts, not confirmed issues.`}>
          <BreakdownList counts={o.review_breakdown} hrefFor={(f) => ex(f)} />
        </Panel>
        <Panel title="Recent activity" subtitle={`Latest verified team-member events at ${site.name} · all events in Activity`}
          action={<Link href="/activity" className="inline-flex min-h-9 items-center gap-0.5 text-xs font-medium text-dt-burnt-orange">All activity <ChevronRight className="size-3" aria-hidden /></Link>}
          bodyClassName="p-0">
          <div className="flex flex-wrap gap-2 border-b border-dt-border/70 px-4 py-2">
            <Link className="inline-flex min-h-9 items-center rounded-full border border-dt-border px-3 text-xs hover:bg-dt-surface-warm" href={hrefWith("/activity", { view: "events", from: site.today, to: site.today })}>Today’s activity</Link>
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
        <HourActivitySheet period={period} hour={Number(s.hour)} mapping={series}
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
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-28" />)}
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
