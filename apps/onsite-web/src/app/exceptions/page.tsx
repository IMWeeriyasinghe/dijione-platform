"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { CheckCircle2, ExternalLink, SearchX } from "lucide-react";
import { DataView, Facts } from "@/components/DataView";
import { EmployeeProfile } from "@/components/EmployeeProfile";
import { ExportButton } from "@/components/ExportButton";
import { DepartmentSelect, IdentitySelect, PeriodControl, SearchField, SelectField, SiteSelect } from "@/components/FilterBar";
import { FlagChips } from "@/components/FlagChips";
import { FreshnessIndicator } from "@/components/FreshnessIndicator";
import { buttonClass, type Chip, cx, EmptyPanel, FilterPanel, focusRing, PageTop, Pager, Person, SkeletonRows } from "@/components/kit";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { getExceptions, REVIEW_FLAGS, type ExceptionItem, type ReviewFlag } from "@/lib/dashboard";
import { addDays, DATA_QUALITY_FLAGS, FLAG_HELP, FLAG_LABEL, formatSpan, localTime } from "@/lib/flags";
import { IDENTITY_LABEL } from "@/lib/format";
import { liveQuery } from "@/lib/live-refresh";
import { fmtDay, fmtNum, fmtPeriod } from "@/lib/period";
import type { IdentityClass } from "@/lib/types";
import { parsePageSize, storedPageSize } from "@/lib/page-size";
import { usePaging } from "@/lib/paging";
import { hrefWith, useUrlState } from "@/lib/url-state";

const SORTS = [
  { value: "-date", label: "Newest day first" },
  { value: "date", label: "Oldest day first" },
  { value: "-flags", label: "Most flags first" },
  { value: "employee", label: "Employee (A–Z)" },
  { value: "-punch_count", label: "Most events first" },
];

function ExceptionsView() {
  const { site } = useSite();
  const [s, set] = useUrlState({ from: addDays(site.today, -6), to: site.today, flag: "", q: "", emp: "", dept: "", id: "", sort: "-date", page: "1", size: storedPageSize("exceptions"), open: "" });
  const page = Math.max(1, Number(s.page) || 1);
  const pageSize = parsePageSize(s.size);
  const filters = { site_id: site.site_id, date_from: s.from, date_to: s.to, flag: s.flag || undefined, q: s.q || undefined,
    emp_code: s.emp.trim() || undefined, department: s.dept || undefined, identity_class: s.id || undefined };
  const params = { ...filters, sort: s.sort, page, page_size: pageSize };
  const query = useQuery({ queryKey: ["onsite-exceptions", params], queryFn: () => getExceptions(params), ...liveQuery });
  const counts = query.data?.counts;
  const totalFlags = counts ? Object.values(counts).reduce((a, b) => a + b, 0) : 0;

  const paging = usePaging("exceptions", s, set, query.data?.total);
  const chips: Chip[] = [
    s.q && { key: "q", label: `Search: ${s.q}`, onClear: () => set({ q: "" }) },
    s.emp && { key: "emp", label: `Employee Number: ${s.emp}`, onClear: () => set({ emp: "" }) },
    s.dept && { key: "dept", label: s.dept, onClear: () => set({ dept: "" }) },
    s.id && { key: "id", label: IDENTITY_LABEL[s.id as IdentityClass] ?? s.id, onClear: () => set({ id: "" }) },
    s.flag && { key: "flag", label: FLAG_LABEL[s.flag as ReviewFlag], onClear: () => set({ flag: "" }) },
  ].filter(Boolean) as Chip[];
  const clearAll = () => set({ q: "", emp: "", dept: "", id: "", flag: "" });

  const actions = (item: ExceptionItem) => (
    <div className="flex flex-wrap gap-2">
      <button type="button" className={buttonClass("secondary")} onClick={() => set({ open: item.emp_code, page: s.page })}>Open employee profile</button>
      <Link href={hrefWith("/activity", { emp: item.emp_code, from: item.local_date, to: item.local_date })} className={buttonClass("ghost")}>
        View supporting events <ExternalLink className="size-3.5" aria-hidden />
      </Link>
    </div>
  );
  const reasons = (item: ExceptionItem) => (
    <ul className="space-y-1 text-sm">
      {item.reasons.map((r) => (
        <li key={r.flag}><span className="font-medium text-dt-text-primary">{FLAG_LABEL[r.flag]}:</span> <span className="text-dt-text-secondary">{r.reason}</span></li>
      ))}
    </ul>
  );

  return (
    <div className="space-y-4">
      <PageTop title="Exceptions"
        description="Employee-days that may need a closer look. Flags are prompts for review only — they are not confirmed policy breaches, and nothing is changed automatically."
        actions={<ExportButton path="exceptions" params={filters} />}>
        <div className="flex flex-wrap items-center gap-2">
          <SiteSelect />
          <PeriodControl value={{ from: s.from, to: s.to }} today={site.today} onChange={(p) => set({ from: p.from, to: p.to })} />
        </div>
        <FreshnessIndicator siteId={site.site_id} queries={[query]} />
      </PageTop>

      <div role="group" aria-label="Filter by review category" className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <CategoryTile active={!s.flag} label="All categories" count={totalFlags} help="Every review flag in the period (an employee-day can carry several)."
          onClick={() => set({ flag: "" })} loading={!counts} />
        {REVIEW_FLAGS.map((f) => (
          <CategoryTile key={f} active={s.flag === f} label={FLAG_LABEL[f]} count={counts?.[f] ?? 0} help={FLAG_HELP[f]} dataQuality={DATA_QUALITY_FLAGS.has(f)}
            onClick={() => set({ flag: s.flag === f ? "" : f })} loading={!counts} />
        ))}
      </div>

      <FilterPanel chips={chips} onClearAll={clearAll}>
        <SearchField label="Search name or code" value={s.q} onChange={(v) => set({ q: v })} />
        <SearchField label="Employee Number" value={s.emp} onChange={(v) => set({ emp: v })} placeholder="Exact number" />
        <DepartmentSelect value={s.dept} onChange={(v) => set({ dept: v })} />
        <IdentitySelect value={s.id} onChange={(v) => set({ id: v })} />
        <SelectField label="Sort by" value={s.sort} onChange={(v) => set({ sort: v })} options={SORTS} />
      </FilterPanel>

      <p className="text-sm text-dt-text-secondary">
        {fmtPeriod({ from: s.from, to: s.to }, site.today)}
        {query.data && <> · <span className="font-semibold text-dt-text-primary">{fmtNum(query.data.total)}</span> employee-days to review</>}
      </p>

      {query.isLoading ? <SkeletonRows label="Loading review queue…" /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> :
        query.data.total === 0 ? (
          chips.length ? (
            <EmptyPanel icon={SearchX} title="Nothing matches these filters" description="No flagged employee-day in this period matches the current filters."
              actions={<button type="button" className={buttonClass("secondary")} onClick={clearAll}>Clear filters</button>} />
          ) : (
            <EmptyPanel icon={CheckCircle2} title="Nothing needs review" description="No recorded day in this period was flagged for review." />
          )
        ) : (
          <>
            <DataView caption="Employee-days flagged for review" rows={query.data.items} rowKey={(i) => `${i.local_date}-${i.emp_code}`}
              rowLabel={(i) => `${i.employee_name ?? i.emp_code} on ${i.local_date}`} sort={s.sort} onSort={(v) => set({ sort: v })}
              columns={[
                { key: "date", header: "Date", sort: "date", cell: (i) => <span className="whitespace-nowrap font-medium">{fmtDay(i.local_date, true)}</span> },
                { key: "emp", header: "Employee", sort: "employee", cell: (i) => <Person photo={i.has_photo} name={i.employee_name} code={i.emp_code} meta={i.department ?? undefined} size="sm" /> },
                { key: "flags", header: "Review flags", sort: "flags", cell: (i) => <FlagChips flags={i.flags} /> },
                { key: "times", header: "First · Latest", minWidth: "lg", cell: (i) => <span className="tabular-nums">{localTime(i.first_activity_local)} · {localTime(i.latest_activity_local)}</span> },
                { key: "count", header: "Events", sort: "punch_count", align: "right", cell: (i) => i.punch_count },
                { key: "terms", header: "Terminals", minWidth: "xl", cell: (i) => i.terminal_names.join(", ") || "—" },
              ]}
              card={(i) => (
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <Person photo={i.has_photo} name={i.employee_name} code={i.emp_code} meta={i.department ?? undefined} size="sm" />
                    <span className="shrink-0 text-xs font-medium text-dt-text-primary">{fmtDay(i.local_date)}</span>
                  </div>
                  <FlagChips flags={i.flags} />
                  <Facts cols={3} items={[["First", localTime(i.first_activity_local)], ["Latest", localTime(i.latest_activity_local)], ["Events", String(i.punch_count)]]} />
                </div>
              )}
              detail={(i) => (
                <div className="space-y-3">
                  {reasons(i)}
                  <Facts cols={4} items={[["First", localTime(i.first_activity_local)], ["Latest", localTime(i.latest_activity_local)],
                    ["Activity span", formatSpan(i.span_minutes)], ["Terminals", i.terminal_names.join(", ") || "—"]]} />
                  {actions(i)}
                </div>
              )} />
            <Pager page={page} pageSize={pageSize} total={query.data.total} onPage={paging.onPage} onPageSize={paging.onPageSize} busy={query.isFetching} noun="employee-day" />
          </>
        )}
      {s.open && <EmployeeProfile code={s.open} to={s.to} onClose={() => set({ open: "", page: s.page })} />}
    </div>
  );
}

function CategoryTile({ active, label, count, help, onClick, loading, dataQuality }: {
  active: boolean; label: string; count: number; help: string; onClick: () => void; loading: boolean; dataQuality?: boolean;
}) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick} title={help}
      className={cx("flex min-h-16 flex-col items-start justify-between rounded-xl border px-3 py-2 text-left transition-colors", focusRing,
        active ? "border-dt-orange bg-dt-cream" : "border-dt-border bg-dt-surface hover:bg-dt-surface-warm",
        !loading && count === 0 && !active && "opacity-60")}>
      <span className="flex items-center gap-1.5 text-xs font-medium text-dt-text-secondary">
        <span aria-hidden className={cx("size-2 rounded-full", dataQuality ? "bg-dt-info/60" : "bg-dt-orange")} />
        {label}
      </span>
      <span className={cx("text-lg font-semibold tabular-nums", active ? "text-dt-burnt-orange" : "text-dt-text-primary")}>{loading ? "…" : fmtNum(count)}</span>
      <span className="sr-only">{help}</span>
    </button>
  );
}

export default function ExceptionsPage() {
  return <SiteProvider><Suspense fallback={<SkeletonRows />}><ExceptionsView /></Suspense></SiteProvider>;
}
