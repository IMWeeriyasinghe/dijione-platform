"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { Activity, SearchX } from "lucide-react";
import { ActivityWho } from "@/components/ActivityRef";
import { DataView, Facts } from "@/components/DataView";
import { EmployeeProfile } from "@/components/EmployeeProfile";
import { ExportReportButton } from "@/components/ReportExportDialog";
import { DailyView } from "./DailyView";
import { DepartmentSelect, IdentitySelect, PeriodControl, SearchField, SelectField, SiteSelect } from "@/components/FilterBar";
import { FlagChips, MappingStateBadge, SequenceMarker } from "@/components/FlagChips";
import { FreshnessIndicator } from "@/components/FreshnessIndicator";
import { buttonClass, cx, EmptyPanel, FilterPanel, focusRing, InfoTip, Pager, PageTop, Segmented, SkeletonRows, type Chip } from "@/components/kit";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { getActivity, VIEWER_REVIEW_FLAGS, type ActivityEvent, type ActivitySummary, type MappingFilter, type ReviewFlag } from "@/lib/dashboard";
import { addDays, FLAG_LABEL, localTime } from "@/lib/flags";
import { formatRecordedSpan, ID_LABELS, IDENTITY_LABEL, MAPPING_FILTER_OPTIONS, MAPPING_STATE, SEQUENCE_LABEL } from "@/lib/format";
import { REVIEW_STATUS_FILTERS } from "@/lib/reviews";
import { liveQuery } from "@/lib/live-refresh";
import { fmtDay, fmtNum, fmtPeriod, fmtShortDay } from "@/lib/period";
import type { IdentityClass } from "@/lib/types";
import { parsePageSize, storedPageSize } from "@/lib/page-size";
import { usePaging } from "@/lib/paging";
import { useUrlState } from "@/lib/url-state";

const MAPPINGS = MAPPING_FILTER_OPTIONS.map((o) => o.value) as readonly string[];

const Who = ActivityWho;

/** Recorded / verified / needs-review counts for the current filters; each
 *  selects that mapping state. Verified + unmapped + conflict = recorded. */
function SummaryStrip({ s, value, onChange }: { s: ActivitySummary; value: string; onChange: (v: MappingFilter) => void }) {
  const items: { key: MappingFilter; label: string; count: number; sub?: string; bar?: string }[] = [
    { key: "all", label: "Recorded events", count: s.recorded, sub: "All mapping states" },
    { key: "verified", label: "Verified", count: s.verified, sub: "Attributed to a team member", bar: MAPPING_STATE.VERIFIED.bar },
    { key: "unverified", label: "Unmapped / needs review", count: s.unverified,
      sub: s.conflict ? `${fmtNum(s.unmapped)} unmapped · ${fmtNum(s.conflict)} conflict` : "No verified mapping that day",
      bar: MAPPING_STATE.UNMAPPED.bar },
  ];
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3" role="group" aria-label="Recorded events by mapping status">
      {items.map((i) => (
        <button key={i.key} type="button" aria-pressed={value === i.key} onClick={() => onChange(i.key)}
          className={cx("rounded-xl border bg-dt-surface p-3 text-left transition-colors hover:bg-dt-surface-warm/60", focusRing,
            value === i.key ? "border-dt-burnt-orange ring-1 ring-dt-burnt-orange/40" : "border-dt-border")}>
          <span className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-dt-text-secondary">
            {i.bar && <span aria-hidden className={cx("size-2.5 rounded-sm", i.bar)} />}
            {i.label}
          </span>
          <span className="mt-1 block text-2xl font-semibold tabular-nums text-dt-text-primary">{fmtNum(i.count)}</span>
          {i.sub && <span className="block text-xs text-dt-text-secondary">{i.sub}</span>}
        </button>
      ))}
    </div>
  );
}

function ActivityView() {
  const { site } = useSite();
  const [s, set] = useUrlState({ view: "daily", from: addDays(site.today, -6), to: site.today, q: "", emp: "", dept: "", term: "", id: "", flag: "", hour: "", mapping: "all", review: "", sort: "-time", dsort: "-date", page: "1", size: storedPageSize("activity"), open: "" });
  const page = Math.max(1, Number(s.page) || 1);
  const pageSize = parsePageSize(s.size);
  // Chart / hour drill-downs always land on individual events.
  const daily = s.view !== "events" && s.hour === "";
  const mapping = (MAPPINGS.includes(s.mapping) ? s.mapping : "all") as MappingFilter;
  const filters = { site_id: site.site_id, date_from: s.from, date_to: s.to, q: s.q || undefined, emp_code: s.emp.trim() || undefined,
    department: s.dept || undefined, terminal: s.term || undefined, identity_class: s.id || undefined, flag: s.flag || undefined,
    hour: s.hour !== "" ? Number(s.hour) : undefined, mapping };
  const dailyFilters = { site_id: site.site_id, date_from: s.from, date_to: s.to, mapping, q: s.q || undefined,
    emp_code: s.emp.trim() || undefined, terminal: s.term || undefined, review_status: s.review || undefined };
  const query = useQuery({ queryKey: ["onsite-activity", filters, s.sort, page, pageSize], queryFn: () => getActivity({ ...filters, sort: s.sort, page, page_size: pageSize }),
    enabled: !daily, ...liveQuery });
  const canInvestigate = Boolean(query.data?.can_investigate_identity);

  const paging = usePaging("activity", s, set, daily ? undefined : query.data?.total);
  const chips: Chip[] = [
    s.q && { key: "q", label: `Search: ${s.q}`, onClear: () => set({ q: "" }) },
    s.emp && { key: "emp", label: `ZKBioTime ID: ${s.emp}`, onClear: () => set({ emp: "" }) },
    s.dept && { key: "dept", label: s.dept, onClear: () => set({ dept: "" }) },
    s.term && { key: "term", label: `Terminal: ${s.term}`, onClear: () => set({ term: "" }) },
    s.id && { key: "id", label: IDENTITY_LABEL[s.id as IdentityClass] ?? s.id, onClear: () => set({ id: "" }) },
    s.flag && { key: "flag", label: `Day flagged: ${FLAG_LABEL[s.flag as ReviewFlag]}`, onClear: () => set({ flag: "" }) },
    s.hour !== "" && { key: "hour", label: `Hour: ${hourLabel(Number(s.hour))}${site.time_zone ? ` (${site.time_zone})` : ""}`, onClear: () => set({ hour: "" }) },
    mapping !== "all" && { key: "mapping", label: MAPPING_FILTER_OPTIONS.find((o) => o.value === mapping)!.label, onClear: () => set({ mapping: "all" }) },
    daily && s.review && { key: "review", label: `Review: ${REVIEW_STATUS_FILTERS.find((o) => o.value === s.review)?.label ?? s.review}`, onClear: () => set({ review: "" }) },
  ].filter(Boolean) as Chip[];
  const clearAll = () => set({ q: "", emp: "", dept: "", term: "", id: "", flag: "", hour: "", mapping: "all", review: "" });
  const verifiedOnlyFilters = Boolean(s.q || s.dept || s.id || (s.flag && s.flag !== "TZ_INCONSISTENT"));

  const detail = (e: ActivityEvent) => {
    const verified = !e.mapping_state || e.mapping_state === "VERIFIED";
    const technical: [string, React.ReactNode][] = [
      ["Time zone check", e.tz_consistent === false ? "Inconsistent with site time zone" : e.tz_consistent ? "Consistent" : "—"],
      ...(e.event_id ? [["Event ID", <span key="i" className="font-mono text-xs">{e.event_id}</span>] as [string, React.ReactNode]] : []),
      ...(e.source_epoch !== undefined ? [["Source epoch", String(e.source_epoch)] as [string, React.ReactNode]] : []),
      ...(e.verify_type !== undefined ? [["Verify type", e.verify_type ?? "—"] as [string, React.ReactNode]] : []),
    ];
    const group = (title: string, items: [React.ReactNode, React.ReactNode][]) => (
      <section aria-label={title} className="space-y-1">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-dt-text-secondary">{title}</h4>
        <Facts cols={4} items={items} />
      </section>
    );
    return (
      <div className="space-y-3">
        {group("Fingerprint record", [
          ["Site-local time", `${fmtDay(e.local_date, true)} ${localTime(e.local_time)}`],
          ["Sequence in the day", e.punch_sequence
            ? `${SEQUENCE_LABEL[e.punch_sequence]} (${e.punch_position} of ${e.punches_in_day})` : "—"],
          ["Day: first / last recorded fingerprint", e.day_first_local
            ? `${localTime(e.day_first_local)} / ${e.punches_in_day === 1 ? "—" : localTime(e.day_last_local)}` : "—"],
          ["Recorded Span (day)", e.day_span_minutes === null || e.day_span_minutes === undefined
            ? "—, Single Recorded Fingerprint" : formatRecordedSpan(e.day_span_minutes)],
        ])}
        {group("Identity", [
          [verified ? "Team member" : "Identity", verified ? (e.employee_name ?? "—") : "Not attributed (raw ID only)"],
          ...(verified ? [[ID_LABELS.bhr, e.bamboohr_id ?? "—"], [ID_LABELS.number, e.employee_number ?? "—"]] as [string, React.ReactNode][] : []),
          ["ZKBioTime ID", <span key="z" className="font-mono">{e.emp_code}</span>],
          ["Mapping status", <MappingStateBadge key="m" state={e.mapping_state} status={e.mapping_status} cls={e.identity_class} />],
        ])}
        {group("Device & source", [
          ["Terminal", e.terminal ?? "—"],
          ["Area", e.area ?? "—"],
          ["Raw device state", <span key="r" className="font-mono" title="Recorded as-is by the terminal; not interpreted">{e.punch_state_raw ?? "—"}</span>],
        ])}
        <details className="text-sm">
          <summary className={cx("cursor-pointer rounded text-xs font-medium text-dt-burnt-orange", focusRing)}>Technical details</summary>
          <div className="mt-2"><Facts cols={4} items={technical} /></div>
        </details>
        <p className="text-xs text-dt-text-secondary">First and last are the first and last recorded fingerprints of this {verified ? "team member's" : "ZKBioTime ID's"} whole site-local day at the entry-side reader. The last recorded fingerprint is not an exit, and the raw device state is limited device data that is not interpreted.</p>
        <div className="flex flex-wrap gap-2">
          {verified && e.bamboohr_id && (
            <button type="button" className={buttonClass("secondary")} onClick={() => set({ open: e.bamboohr_id ?? "", page: s.page })}>Open team member profile</button>
          )}
          <button type="button" className={buttonClass("ghost")} onClick={() => set({ emp: e.emp_code, from: e.local_date, to: e.local_date, mapping: "all" })}>
            Only ZKBioTime ID {e.emp_code} on {fmtShortDay(e.local_date)}
          </button>
          {!verified && canInvestigate && (
            <Link href={`/admin/identity?code=${encodeURIComponent(e.emp_code)}`} className={buttonClass("secondary")}>
              Investigate in Identity Management
            </Link>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <PageTop title="Activity"
        description="Every recorded fingerprint in site-local time — verified and unverified — as a daily summary per identity or as individual events. Unverified fingerprints show their ZKBioTime ID only and are never attributed to a team member. Recorded at the entry-side reader: not a confirmed exit, presence or hours worked."
        actions={<ExportReportButton terminals={site.terminals} departments={site.departments ?? []} context={{
          report: daily ? "daily" : mapping === "verified" ? "verified" : "recorded", siteId: site.site_id, today: site.today,
          from: s.from, to: s.to, q: s.q, emp: s.emp, mapping, dept: s.dept, term: s.term, flag: s.flag, review: s.review }} />}>
        <div className="flex flex-wrap items-center gap-2">
          <SiteSelect />
          <PeriodControl value={{ from: s.from, to: s.to }} today={site.today} onChange={(p) => set({ from: p.from, to: p.to })} />
        </div>
        <FreshnessIndicator siteId={site.site_id} queries={[query]} />
      </PageTop>

      <div className="flex flex-wrap items-center gap-2">
        <Segmented label="View" value={daily ? "daily" : "events"} onChange={(v) => set({ view: v, page: "1" })}
          options={[{ value: "daily", label: "Daily summary" }, { value: "events", label: "Events" }]} />
        <Segmented label="Mapping status" value={mapping} onChange={(v) => set({ mapping: v, page: "1" })}
          options={MAPPING_FILTER_OPTIONS.map((o) => ({ value: o.value, label: o.label }))} />
        <InfoTip label="About mapping status" text="Each event is classified by the mapping valid on its own site-local day. Verified events are attributed to a team member; unmapped and conflicting events are shown by ZKBioTime ID only. A conflict is never attributed." />
      </div>

      {!daily && query.data?.summary && <SummaryStrip s={query.data.summary} value={mapping} onChange={(v) => set({ mapping: v, page: "1" })} />}

      <FilterPanel chips={chips} onClearAll={clearAll}
        summary={!daily && query.data ? <span className="text-xs text-dt-text-secondary">{fmtNum(query.data.total)} events</span> : undefined}>
        <SearchField label="Search name, BHR ID or EMP Number" value={s.q} onChange={(v) => set({ q: v })}
          placeholder="Verified team members only" />
        <SearchField label="ZKBioTime ID" value={s.emp} onChange={(v) => set({ emp: v })} placeholder="Exact ID, any status" />
        <SelectField label="Terminal" value={s.term} onChange={(v) => set({ term: v })}
          options={[{ value: "", label: "All terminals" }, ...site.terminals.map((t) => ({ value: t, label: t }))]} />
        {daily ? (
          <SelectField label="Review status" value={s.review} onChange={(v) => set({ review: v })}
            options={REVIEW_STATUS_FILTERS.map((o) => ({ value: o.value, label: o.label }))} />
        ) : (
          <>
            <DepartmentSelect value={s.dept} onChange={(v) => set({ dept: v })} />
            <IdentitySelect value={s.id} onChange={(v) => set({ id: v })} label="Verified team member status" anyLabel="Any" />
            <SelectField label="Hour of day" value={s.hour} onChange={(v) => set({ hour: v })}
              options={[{ value: "", label: "Any hour" }, ...Array.from({ length: 24 }, (_, h) => ({ value: String(h), label: hourLabel(h) }))]} />
            <SelectField label="Order" value={s.sort} onChange={(v) => set({ sort: v })}
              options={[{ value: "-time", label: "Newest first" }, { value: "time", label: "Oldest first" }]} />
            <SelectField label="Day review flag" value={s.flag} onChange={(v) => set({ flag: v })}
              options={[{ value: "", label: "Any" }, ...VIEWER_REVIEW_FLAGS.map((f) => ({ value: f, label: FLAG_LABEL[f] }))]} />
          </>
        )}
      </FilterPanel>
      {verifiedOnlyFilters && mapping !== "verified" && (
        <p className="text-xs text-dt-text-secondary">Name, BHR ID, EMP Number, department, team member status and day review filters only match verified events.</p>
      )}

      <p className="text-sm text-dt-text-secondary">
        {fmtPeriod({ from: s.from, to: s.to }, site.today)}
        {!daily && query.data && <> · <span className="font-semibold text-dt-text-primary">{fmtNum(query.data.total)}</span> {mapping === "all" ? "recorded events" : `${MAPPING_FILTER_OPTIONS.find((o) => o.value === mapping)!.label.toLowerCase()} events`}</>}
      </p>

      {daily ? (
        <DailyView filters={dailyFilters} sort={s.dsort} onSort={(v) => set({ dsort: v })} page={page} pageSize={pageSize}
          onPage={paging.onPage} onPageSize={paging.onPageSize} today={site.today}
          onEvents={(r) => set({ view: "events", from: r.local_date, to: r.local_date, page: "1",
            ...(r.mapping_state === "VERIFIED" ? { q: r.bamboohr_id ?? "", emp: "", mapping: "verified" } : { emp: r.emp_code, q: "", mapping: "all" }) })} />
      ) : query.isLoading ?<SkeletonRows label="Loading activity…" /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> :
        query.data.total === 0 ? (
          chips.length ? (
            <EmptyPanel icon={SearchX} title="No events match these filters" description="Try removing a filter, choosing All activity or widening the period."
              actions={<button type="button" className={buttonClass("secondary")} onClick={clearAll}>Clear filters</button>} />
          ) : (
            <EmptyPanel icon={Activity} title="No activity recorded in this period" description="No terminal activity was recorded for this site in the selected period."
              actions={site.last_activity_date ? (
                <button type="button" className={buttonClass("secondary")} onClick={() => set({ from: addDays(site.last_activity_date!, -6), to: site.last_activity_date! })}>
                  Show the 7 days to {fmtDay(site.last_activity_date)}
                </button>
              ) : undefined} />
          )
        ) : (
          <>
            {!query.data.directory_available && <p className="text-sm text-dt-burnt-orange">Team member details unavailable — verified attendance is shown without names.</p>}
            <DataView caption="Recorded activity events" rows={query.data.items}
              rowKey={(e) => e.event_id ?? `${e.emp_code}-${e.local_time}`}
              rowLabel={(e) => `${e.mapping_state && e.mapping_state !== "VERIFIED" ? `ZKBioTime ID ${e.emp_code}` : e.employee_name ?? e.emp_code} at ${localTime(e.local_time)}`}
              columns={[
                { key: "time", header: "Site-local time", nowrap: true, cell: (e) => (
                  <span><span className="font-medium tabular-nums text-dt-text-primary">{localTime(e.local_time)}</span>
                    <span className="ml-1.5 text-xs text-dt-text-secondary">{e.local_date === site.today ? "Today" : fmtDay(e.local_date)}</span></span>
                ) },
                { key: "emp", header: "Team Member / ID", cell: (e) => <Who e={e} /> },
                { key: "term", header: "Terminal", cell: (e) => <span className="text-dt-text-primary">{e.terminal ?? "—"}{e.area && <span className="block text-xs text-dt-text-secondary">{e.area}</span>}</span> },
                { key: "id", header: "Mapping Status", nowrap: true, cell: (e) => <MappingStateBadge state={e.mapping_state} status={e.mapping_status} cls={e.identity_class} /> },
                { key: "seq", header: "Punch in day", minWidth: "xl", help: "First and last recorded fingerprint of the whole site-local day for this team member (or ZKBioTime ID). Recorded order only — the last fingerprint is not an exit.",
                  cell: (e) => <SequenceMarker seq={e.punch_sequence} position={e.punch_position} total={e.punches_in_day} /> },
                { key: "flags", header: "Review", minWidth: "xl", cell: (e) => <FlagChips flags={e.review_flags ?? []} /> },
                { key: "raw", header: "Raw state", minWidth: "2xl", nowrap: true, cell: (e) => <span className="font-mono text-xs">{e.punch_state_raw ?? "—"}</span> },
              ]}
              card={(e) => (
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <Who e={e} />
                    <span className="shrink-0 text-right">
                      <span className="block font-semibold tabular-nums text-dt-text-primary">{localTime(e.local_time)}</span>
                      <span className="block text-xs text-dt-text-secondary">{e.local_date === site.today ? "Today" : fmtDay(e.local_date)}</span>
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-dt-text-secondary">
                    <span>{e.terminal ?? "Unknown terminal"}</span>
                    <MappingStateBadge state={e.mapping_state} status={e.mapping_status} cls={e.identity_class} />
                    <SequenceMarker seq={e.punch_sequence} />
                  </div>
                  {(e.review_flags ?? []).length > 0 && <FlagChips flags={e.review_flags ?? []} />}
                </div>
              )}
              detail={detail} />
            <Pager page={page} pageSize={pageSize} total={query.data.total} onPage={paging.onPage} onPageSize={paging.onPageSize} busy={query.isFetching} noun="event" />
          </>
        )}
      {s.open && <EmployeeProfile code={s.open} to={s.to} onClose={() => set({ open: "", page: s.page })} />}
    </div>
  );
}

/** "11:00–11:59" — a site-local clock hour. */
export function hourLabel(h: number): string {
  const hh = String(h).padStart(2, "0");
  return `${hh}:00–${hh}:59`;
}

export default function ActivityPage() {
  return <SiteProvider><Suspense fallback={<SkeletonRows />}><ActivityView /></Suspense></SiteProvider>;
}
