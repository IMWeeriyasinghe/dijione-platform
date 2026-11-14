"use client";

import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { Activity, SearchX } from "lucide-react";
import { DataView, Facts } from "@/components/DataView";
import { EmployeeProfile } from "@/components/EmployeeProfile";
import { ExportButton } from "@/components/ExportButton";
import { DepartmentSelect, IdentitySelect, PeriodControl, SearchField, SelectField, SiteSelect } from "@/components/FilterBar";
import { FlagChips, MappingBadge } from "@/components/FlagChips";
import { FreshnessIndicator } from "@/components/FreshnessIndicator";
import { buttonClass, EmployeeRefCell, EmptyPanel, FilterPanel, Pager, PageTop, SkeletonRows, type Chip } from "@/components/kit";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { getActivity, VIEWER_REVIEW_FLAGS, type ActivityEvent, type ReviewFlag } from "@/lib/dashboard";
import { addDays, FLAG_LABEL, localTime } from "@/lib/flags";
import { IDENTITY_LABEL } from "@/lib/format";
import { liveQuery } from "@/lib/live-refresh";
import { fmtDay, fmtNum, fmtPeriod, fmtShortDay } from "@/lib/period";
import type { IdentityClass } from "@/lib/types";
import { parsePageSize, storedPageSize } from "@/lib/page-size";
import { usePaging } from "@/lib/paging";
import { useUrlState } from "@/lib/url-state";


function ActivityView() {
  const { site } = useSite();
  const [s, set] = useUrlState({ from: addDays(site.today, -6), to: site.today, q: "", emp: "", dept: "", term: "", id: "", flag: "", hour: "", sort: "-time", page: "1", size: storedPageSize("activity"), open: "" });
  const page = Math.max(1, Number(s.page) || 1);
  const pageSize = parsePageSize(s.size);
  const filters = { site_id: site.site_id, date_from: s.from, date_to: s.to, q: s.q || undefined, emp_code: s.emp.trim() || undefined,
    department: s.dept || undefined, terminal: s.term || undefined, identity_class: s.id || undefined, flag: s.flag || undefined,
    hour: s.hour !== "" ? Number(s.hour) : undefined };
  const query = useQuery({ queryKey: ["onsite-activity", filters, s.sort, page, pageSize], queryFn: () => getActivity({ ...filters, sort: s.sort, page, page_size: pageSize }), ...liveQuery });

  const paging = usePaging("activity", s, set, query.data?.total);
  const chips: Chip[] = [
    s.q && { key: "q", label: `Search: ${s.q}`, onClear: () => set({ q: "" }) },
    s.emp && { key: "emp", label: `ZKBioTime ID: ${s.emp}`, onClear: () => set({ emp: "" }) },
    s.dept && { key: "dept", label: s.dept, onClear: () => set({ dept: "" }) },
    s.term && { key: "term", label: `Terminal: ${s.term}`, onClear: () => set({ term: "" }) },
    s.id && { key: "id", label: IDENTITY_LABEL[s.id as IdentityClass] ?? s.id, onClear: () => set({ id: "" }) },
    s.flag && { key: "flag", label: `Day flagged: ${FLAG_LABEL[s.flag as ReviewFlag]}`, onClear: () => set({ flag: "" }) },
    s.hour !== "" && { key: "hour", label: `Hour: ${hourLabel(Number(s.hour))}${site.time_zone ? ` (${site.time_zone})` : ""}`, onClear: () => set({ hour: "" }) },
  ].filter(Boolean) as Chip[];
  const clearAll = () => set({ q: "", emp: "", dept: "", term: "", id: "", flag: "", hour: "" });

  const detail = (e: ActivityEvent) => (
    <div className="space-y-3">
      <Facts cols={4} items={[
        ["Site-local time", `${fmtDay(e.local_date, true)} ${localTime(e.local_time)}`],
        ["Terminal", e.terminal ?? "—"],
        ["Area", e.area ?? "—"],
        ["Raw device state", <span key="r" className="font-mono" title="Recorded as-is by the terminal; not interpreted as check-in/out">{e.punch_state_raw ?? "—"}</span>],
        ["Time zone check", e.tz_consistent === false ? "Inconsistent with site time zone" : e.tz_consistent ? "Consistent" : "—"],
        ...(e.event_id ? [["Event ID", <span key="i" className="font-mono text-xs">{e.event_id}</span>] as [string, React.ReactNode]] : []),
        ...(e.source_epoch !== undefined ? [["Source epoch", String(e.source_epoch)] as [string, React.ReactNode]] : []),
        ...(e.verify_type !== undefined ? [["Verify type", e.verify_type ?? "—"] as [string, React.ReactNode]] : []),
      ]} />
      <div className="flex flex-wrap gap-2">
        <button type="button" className={buttonClass("secondary")} onClick={() => set({ open: e.bamboohr_id ?? "", page: s.page })}>Open employee profile</button>
        <button type="button" className={buttonClass("ghost")} onClick={() => set({ emp: e.emp_code, from: e.local_date, to: e.local_date })}>
          Only this employee on {fmtShortDay(e.local_date)}
        </button>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <PageTop title="Activity"
        description="Every recorded attendance event, newest first, in site-local time. The raw device state is shown as recorded and is not interpreted as check-in or check-out."
        actions={<ExportButton path="activity" params={filters} />}>
        <div className="flex flex-wrap items-center gap-2">
          <SiteSelect />
          <PeriodControl value={{ from: s.from, to: s.to }} today={site.today} onChange={(p) => set({ from: p.from, to: p.to })} />
        </div>
        <FreshnessIndicator siteId={site.site_id} queries={[query]} />
      </PageTop>

      <FilterPanel chips={chips} onClearAll={clearAll}
        summary={query.data ? <span className="text-xs text-dt-text-secondary">{fmtNum(query.data.total)} events</span> : undefined}>
        <SearchField label="Search name, BHR ID or Employee Number" value={s.q} onChange={(v) => set({ q: v })} />
        <SearchField label="ZKBioTime ID" value={s.emp} onChange={(v) => set({ emp: v })} placeholder="Exact ID" />
        <DepartmentSelect value={s.dept} onChange={(v) => set({ dept: v })} />
        <SelectField label="Terminal" value={s.term} onChange={(v) => set({ term: v })}
          options={[{ value: "", label: "All terminals" }, ...site.terminals.map((t) => ({ value: t, label: t }))]} />
        <IdentitySelect value={s.id} onChange={(v) => set({ id: v })} />
        <SelectField label="Hour of day" value={s.hour} onChange={(v) => set({ hour: v })}
          options={[{ value: "", label: "Any hour" }, ...Array.from({ length: 24 }, (_, h) => ({ value: String(h), label: hourLabel(h) }))]} />
        <SelectField label="Order" value={s.sort} onChange={(v) => set({ sort: v })}
          options={[{ value: "-time", label: "Newest first" }, { value: "time", label: "Oldest first" }]} />
        <SelectField label="Day review flag" value={s.flag} onChange={(v) => set({ flag: v })}
          options={[{ value: "", label: "Any" }, ...VIEWER_REVIEW_FLAGS.map((f) => ({ value: f, label: FLAG_LABEL[f] }))]} />
      </FilterPanel>

      <p className="text-sm text-dt-text-secondary">
        {fmtPeriod({ from: s.from, to: s.to }, site.today)}
        {query.data && <> · <span className="font-semibold text-dt-text-primary">{fmtNum(query.data.total)}</span> recorded events</>}
      </p>

      {query.isLoading ? <SkeletonRows label="Loading activity…" /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> :
        query.data.total === 0 ? (
          chips.length ? (
            <EmptyPanel icon={SearchX} title="No events match these filters" description="Try removing a filter or widening the period."
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
            {!query.data.directory_available && <p className="text-sm text-dt-burnt-orange">Employee details unavailable — verified attendance is shown without names.</p>}
            <DataView caption="Recorded activity events" rows={query.data.items}
              rowKey={(e) => e.event_id ?? `${e.emp_code}-${e.local_time}`} rowLabel={(e) => `${e.employee_name ?? e.emp_code} at ${localTime(e.local_time)}`}
              columns={[
                { key: "time", header: "Site-local time", cell: (e) => (
                  <span className="whitespace-nowrap"><span className="font-medium tabular-nums text-dt-text-primary">{localTime(e.local_time)}</span>
                    <span className="ml-1.5 text-xs text-dt-text-secondary">{e.local_date === site.today ? "Today" : fmtDay(e.local_date)}</span></span>
                ) },
                { key: "emp", header: "Employee", cell: (e) => <EmployeeRefCell r={e} meta={e.department ?? undefined} size="sm" /> },
                { key: "term", header: "Terminal", cell: (e) => <span className="text-dt-text-primary">{e.terminal ?? "—"}{e.area && <span className="block text-xs text-dt-text-secondary">{e.area}</span>}</span> },
                { key: "id", header: "Mapping Status", cell: (e) => <MappingBadge status={e.mapping_status} cls={e.identity_class} /> },
                { key: "flags", header: "Review", minWidth: "lg", cell: (e) => <FlagChips flags={e.review_flags ?? []} /> },
                { key: "raw", header: "Raw state", minWidth: "xl", cell: (e) => <span className="font-mono text-xs">{e.punch_state_raw ?? "—"}</span> },
              ]}
              card={(e) => (
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <EmployeeRefCell r={e} meta={e.department ?? undefined} size="sm" />
                    <span className="shrink-0 text-right">
                      <span className="block font-semibold tabular-nums text-dt-text-primary">{localTime(e.local_time)}</span>
                      <span className="block text-xs text-dt-text-secondary">{e.local_date === site.today ? "Today" : fmtDay(e.local_date)}</span>
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-dt-text-secondary">
                    <span>{e.terminal ?? "Unknown terminal"}</span>
                    <MappingBadge status={e.mapping_status} cls={e.identity_class} />
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
