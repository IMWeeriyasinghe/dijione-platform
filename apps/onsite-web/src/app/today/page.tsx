"use client";

import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { CalendarDays, SearchX } from "lucide-react";
import { DataView, Facts } from "@/components/DataView";
import { EmployeeProfile } from "@/components/EmployeeProfile";
import { ExportButton } from "@/components/ExportButton";
import { DayControl, DepartmentSelect, IdentitySelect, SearchField, SelectField, SiteSelect } from "@/components/FilterBar";
import { FlagChips } from "@/components/FlagChips";
import { FreshnessIndicator } from "@/components/FreshnessIndicator";
import { buttonClass, EmployeeRefCell, EmptyPanel, FilterPanel, InfoTip, Pager, PageTop, Segmented, SkeletonRows, type Chip } from "@/components/kit";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { getToday, VIEWER_REVIEW_FLAGS, type ReviewFlag } from "@/lib/dashboard";
import { FLAG_LABEL, formatSpan, localTime } from "@/lib/flags";
import { IDENTITY_LABEL } from "@/lib/format";
import { liveQuery } from "@/lib/live-refresh";
import { fmtDay, fmtNum } from "@/lib/period";
import type { IdentityClass } from "@/lib/types";
import { parsePageSize, storedPageSize } from "@/lib/page-size";
import { usePaging } from "@/lib/paging";
import { useUrlState } from "@/lib/url-state";

const SORTS = [
  { value: "first_activity", label: "First activity (earliest)" },
  { value: "-latest_activity", label: "Latest activity (latest)" },
  { value: "-punch_count", label: "Events (most)" },
  { value: "-span", label: "Activity span (longest)" },
  { value: "employee", label: "Employee (A–Z)" },
  { value: "-flags", label: "Review flags (most)" },
];

function TodayView() {
  const { site } = useSite();
  const [s, set] = useUrlState({ date: site.today, q: "", emp: "", dept: "", id: "", review: "", sort: "first_activity", page: "1", size: storedPageSize("today"), open: "" });
  const page = Math.max(1, Number(s.page) || 1);
  const pageSize = parsePageSize(s.size);
  const filters = { site_id: site.site_id, date: s.date, q: s.q || undefined, emp_code: s.emp.trim() || undefined, department: s.dept || undefined,
    identity_class: s.id || undefined, review: s.review || undefined };
  const params = { ...filters, sort: s.sort, page, page_size: pageSize };
  const query = useQuery({ queryKey: ["onsite-today", params], queryFn: () => getToday(params), ...liveQuery });

  const paging = usePaging("today", s, set, query.data?.total);
  const chips: Chip[] = [
    s.q && { key: "q", label: `Search: ${s.q}`, onClear: () => set({ q: "" }) },
    s.emp && { key: "emp", label: `ZKBioTime ID: ${s.emp}`, onClear: () => set({ emp: "" }) },
    s.dept && { key: "dept", label: s.dept, onClear: () => set({ dept: "" }) },
    s.id && { key: "id", label: IDENTITY_LABEL[s.id as IdentityClass] ?? s.id, onClear: () => set({ id: "" }) },
    s.review && !["needs_review", "no_flags"].includes(s.review) && { key: "review", label: FLAG_LABEL[s.review as ReviewFlag], onClear: () => set({ review: "" }) },
  ].filter(Boolean) as Chip[];
  const clearAll = () => set({ q: "", emp: "", dept: "", id: "", review: "" });
  const isToday = s.date === site.today;

  return (
    <div className="space-y-4">
      <PageTop title="Today"
        description={<>First and latest recorded activity and event count per employee, for one site-local day{site.time_zone ? ` (${site.time_zone})` : ""}.</>}
        actions={<ExportButton path="today" params={filters} />}>
        <div className="flex flex-wrap items-center gap-2">
          <SiteSelect />
          <DayControl value={s.date} today={site.today} latest={site.last_activity_date} onChange={(d) => set({ date: d })} />
        </div>
        <FreshnessIndicator siteId={site.site_id} queries={[query]} />
      </PageTop>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-dt-text-secondary">
          <span className="font-semibold text-dt-text-primary">{fmtDay(s.date, true)}</span>{isToday && " · today, in progress"}
          {query.data && <> · <span className="font-semibold text-dt-text-primary">{fmtNum(query.data.total)}</span> employees with recorded activity</>}
        </p>
        <Segmented label="Review status" value={["needs_review", "no_flags"].includes(s.review) ? s.review : ""}
          onChange={(v) => set({ review: v })}
          options={[{ value: "", label: "All" }, { value: "needs_review", label: "Needs review" }, { value: "no_flags", label: "No flags" }]} />
      </div>

      <FilterPanel chips={chips} onClearAll={clearAll}>
        <SearchField label="Search name, BHR ID or Employee Number" value={s.q} onChange={(v) => set({ q: v })} />
        <SearchField label="ZKBioTime ID" value={s.emp} onChange={(v) => set({ emp: v })} placeholder="Exact ID" />
        <DepartmentSelect value={s.dept} onChange={(v) => set({ dept: v })} departments={query.data?.departments} />
        <IdentitySelect value={s.id} onChange={(v) => set({ id: v })} />
        <SelectField label="Review flag" value={["needs_review", "no_flags"].includes(s.review) ? "" : s.review} onChange={(v) => set({ review: v })}
          options={[{ value: "", label: "Any flag" }, ...VIEWER_REVIEW_FLAGS.map((f) => ({ value: f, label: FLAG_LABEL[f] }))]} />
        <SelectField label="Sort by" value={s.sort} onChange={(v) => set({ sort: v })} options={SORTS} />
      </FilterPanel>

      {query.isLoading ? <SkeletonRows label="Loading activity…" /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> :
        query.data.total === 0 ? (
          chips.length || s.review ? (
            <EmptyPanel icon={SearchX} title="No employees match these filters" description={`Nothing recorded on ${fmtDay(s.date)} matches the current filters.`}
              actions={<button type="button" className={buttonClass("secondary")} onClick={() => set({ q: "", emp: "", dept: "", id: "", review: "" })}>Clear filters</button>} />
          ) : (
            <EmptyPanel icon={CalendarDays} title={isToday ? "No activity recorded yet today" : "No activity recorded on this day"}
              description={<>{isToday ? "Activity appears here within about two minutes of a fingerprint punch." : "No terminal activity was recorded for this site on this day."} This is not an absence record.</>}
              actions={site.last_activity_date && site.last_activity_date !== s.date ? (
                <button type="button" className={buttonClass("secondary")} onClick={() => set({ date: site.last_activity_date! })}>
                  Go to latest activity day ({fmtDay(site.last_activity_date)})
                </button>
              ) : undefined} />
          )
        ) : (
          <>
            {!query.data.directory_available && <p className="text-sm text-dt-burnt-orange">Employee details unavailable — verified attendance is shown without names.</p>}
            <DataView caption={`Employee activity on ${s.date}`} rows={query.data.items} rowKey={(r) => r.emp_code}
              rowLabel={(r) => r.employee_name ?? r.emp_code} onRowClick={(r) => set({ open: r.bamboohr_id ?? "", page: s.page })}
              sort={s.sort} onSort={(v) => set({ sort: v })}
              columns={[
                { key: "emp", header: "Employee", sort: "employee", cell: (r) => <EmployeeRefCell r={r} meta={r.department ?? undefined} /> },
                { key: "first", header: "First", sort: "first_activity", cell: (r) => <span className="tabular-nums">{localTime(r.first_activity_local)}</span> },
                { key: "latest", header: "Latest", sort: "latest_activity", cell: (r) => <span className="tabular-nums">{localTime(r.latest_activity_local)}</span> },
                { key: "count", header: "Events", sort: "punch_count", align: "right", cell: (r) => r.punch_count },
                { key: "span", header: <span className="inline-flex items-center gap-1">Activity span <InfoTip text="First to latest recorded activity. Not worked hours." /></span>, sort: "span", minWidth: "lg", cell: (r) => formatSpan(r.span_minutes) },
                { key: "terms", header: "Terminals", minWidth: "xl", cell: (r) => r.terminal_names.join(", ") || "—" },
                { key: "flags", header: "Review", sort: "flags", cell: (r) => <FlagChips flags={r.flags} /> },
              ]}
              card={(r) => (
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <EmployeeRefCell r={r} meta={r.department ?? undefined} />
                    <span className="shrink-0 rounded-full bg-dt-surface-warm px-2 py-0.5 text-xs font-medium tabular-nums text-dt-text-primary">{r.punch_count} events</span>
                  </div>
                  <Facts cols={3} items={[["First", localTime(r.first_activity_local)], ["Latest", localTime(r.latest_activity_local)], ["Span", formatSpan(r.span_minutes)]]} />
                  {r.flags.length > 0 && <FlagChips flags={r.flags} />}
                </div>
              )} />
            <Pager page={page} pageSize={pageSize} total={query.data.total} onPage={paging.onPage} onPageSize={paging.onPageSize} busy={query.isFetching} noun="employee" />
          </>
        )}
      {s.open && <EmployeeProfile code={s.open} to={s.date} onClose={() => set({ open: "", page: s.page })} />}
    </div>
  );
}

export default function TodayPage() {
  return <SiteProvider><Suspense fallback={<SkeletonRows />}><TodayView /></Suspense></SiteProvider>;
}
