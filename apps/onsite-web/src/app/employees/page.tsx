"use client";

import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { SearchX, Users } from "lucide-react";
import { DataView, Facts } from "@/components/DataView";
import { EmployeeProfile } from "@/components/EmployeeProfile";
import { ExportButton } from "@/components/ExportButton";
import { DepartmentSelect, IdentitySelect, PeriodControl, SearchField, SelectField, SiteSelect } from "@/components/FilterBar";
import { IdentityBadge } from "@/components/FlagChips";
import { FreshnessIndicator } from "@/components/FreshnessIndicator";
import { buttonClass, type Chip, EmptyPanel, FilterPanel, InfoTip, PageTop, Pager, Person, SkeletonRows } from "@/components/kit";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { ToneBadge } from "@/components/ToneBadge";
import { getEmployees, type EmployeeRow, type EmployeesSummary } from "@/lib/dashboard";
import { addDays, localTime } from "@/lib/flags";
import { IDENTITY_LABEL } from "@/lib/format";
import { liveQuery } from "@/lib/live-refresh";
import { fmtNum, fmtPeriod, fmtShortDay } from "@/lib/period";
import type { IdentityClass } from "@/lib/types";
import { parsePageSize, storedPageSize } from "@/lib/page-size";
import { usePaging } from "@/lib/paging";
import { useUrlState } from "@/lib/url-state";

const ACTIVITY_LABEL: Record<string, string> = { with_activity: "Activity recorded", no_activity: "No activity recorded", all: "Everyone" };

function lastActivity(r: EmployeeRow): string {
  return r.last_activity_local ? `${fmtShortDay(r.last_activity_local.slice(0, 10))} ${localTime(r.last_activity_local)}` : "—";
}

function StatusBadge({ r }: { r: EmployeeRow }) {
  if (!r.in_directory) return <ToneBadge tone="danger">Not in directory</ToneBadge>;
  if (!r.employment_status) return <span className="text-dt-text-secondary">—</span>;
  return <ToneBadge tone={r.employment_status.toLowerCase() === "active" ? "success" : "neutral"}>{r.employment_status}</ToneBadge>;
}

function SummaryTiles({ s, period }: { s: EmployeesSummary; period: string }) {
  const coverage = s.employees ? Math.round((s.matched / s.employees) * 100) : 0;
  const tiles: [string, string, string][] = [
    ["Employees in view", fmtNum(s.employees), "Workforce Directory employees with an Employee Number, plus attendance codes with no directory match, after your filters."],
    ["With recorded activity", fmtNum(s.with_activity), `Employees in view with at least one recorded activity in ${period}.`],
    ["Active · Inactive", `${fmtNum(s.active)} · ${fmtNum(s.inactive)}`, "Employment status from the Workforce Directory (BambooHR)."],
    ["Needing review", fmtNum(s.needing_review), "Employees in view with at least one review flag in the period. Flags are prompts, not confirmed issues."],
    ["Identity matched", `${coverage}%`, `${fmtNum(s.matched)} of ${fmtNum(s.employees)} matched to exactly one directory record by Employee Number; ${fmtNum(s.not_in_directory)} attendance codes are not in the directory.`],
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
      {tiles.map(([label, value, help]) => (
        <div key={label} className="rounded-xl border border-dt-border bg-dt-surface px-3 py-2.5">
          <dt className="flex items-center gap-1 text-xs text-dt-text-secondary">{label}<InfoTip text={help} label={`About ${label}`} /></dt>
          <dd className="mt-0.5 text-lg font-semibold tabular-nums text-dt-text-primary">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function EmployeesView() {
  const { site } = useSite();
  const [s, set] = useUrlState({ from: addDays(site.today, -29), to: site.today, q: "", emp: "", dept: "", id: "", status: "", act: "with_activity",
    sort: "-events", page: "1", size: storedPageSize("employees"), open: "" });
  const page = Math.max(1, Number(s.page) || 1);
  const pageSize = parsePageSize(s.size);
  const filters = { site_id: site.site_id, date_from: s.from, date_to: s.to, q: s.q || undefined, emp_code: s.emp.trim() || undefined,
    department: s.dept || undefined, identity_class: s.id || undefined, employment_status: s.status || undefined,
    activity: s.act === "all" ? undefined : s.act };
  const params = { ...filters, sort: s.sort, page, page_size: pageSize };
  const query = useQuery({ queryKey: ["onsite-employees", params], queryFn: () => getEmployees(params), ...liveQuery });
  const periodLabel = fmtPeriod({ from: s.from, to: s.to }, site.today);

  const paging = usePaging("employees", s, set, query.data?.total);
  const chips: Chip[] = [
    s.q && { key: "q", label: `Search: ${s.q}`, onClear: () => set({ q: "" }) },
    s.emp && { key: "emp", label: `Employee Number: ${s.emp}`, onClear: () => set({ emp: "" }) },
    s.dept && { key: "dept", label: s.dept, onClear: () => set({ dept: "" }) },
    s.id && { key: "id", label: IDENTITY_LABEL[s.id as IdentityClass] ?? s.id, onClear: () => set({ id: "" }) },
    s.status && { key: "status", label: s.status, onClear: () => set({ status: "" }) },
    s.act !== "with_activity" && { key: "act", label: ACTIVITY_LABEL[s.act] ?? s.act, onClear: () => set({ act: "with_activity" }) },
  ].filter(Boolean) as Chip[];
  const clearAll = () => set({ q: "", emp: "", dept: "", id: "", status: "", act: "with_activity" });

  return (
    <div className="space-y-4">
      <PageTop title="Employees"
        description="Recorded attendance activity per employee. Employees are matched to the Workforce Directory by exact Employee Number."
        actions={<ExportButton path="employees" params={filters} />}>
        <div className="flex flex-wrap items-center gap-2">
          <SiteSelect />
          <PeriodControl value={{ from: s.from, to: s.to }} today={site.today} onChange={(p) => set({ from: p.from, to: p.to })} />
        </div>
        <FreshnessIndicator siteId={site.site_id} queries={[query]} />
      </PageTop>

      {query.data?.summary && <SummaryTiles s={query.data.summary} period={periodLabel} />}

      <FilterPanel chips={chips} onClearAll={clearAll}>
        <SearchField label="Search name or code" value={s.q} onChange={(v) => set({ q: v })} />
        <SearchField label="Employee Number" value={s.emp} onChange={(v) => set({ emp: v })} placeholder="Exact number" />
        <DepartmentSelect value={s.dept} onChange={(v) => set({ dept: v })} departments={query.data?.departments} />
        <SelectField label="Employment status" value={s.status} onChange={(v) => set({ status: v })}
          options={[{ value: "", label: "Any status" }, { value: "Active", label: "Active" }, { value: "Inactive", label: "Inactive" }]} />
        <IdentitySelect value={s.id} onChange={(v) => set({ id: v })} />
        <SelectField label="Activity in period" value={s.act} onChange={(v) => set({ act: v })}
          options={[{ value: "with_activity", label: "Activity recorded" }, { value: "no_activity", label: "No activity recorded" }, { value: "all", label: "Everyone" }]} />
      </FilterPanel>

      {query.isLoading ? <SkeletonRows label="Loading employees…" /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> :
        query.data.total === 0 ? (
          chips.length ? (
            <EmptyPanel icon={SearchX} title="No employees match these filters" description={`Nothing matches in ${periodLabel}.`}
              actions={<button type="button" className={buttonClass("secondary")} onClick={clearAll}>Clear filters</button>} />
          ) : (
            <EmptyPanel icon={Users} title="No recorded activity in this period" description="No employee has recorded activity at this site in the selected period."
              actions={<button type="button" className={buttonClass("secondary")} onClick={() => set({ act: "all" })}>Show everyone</button>} />
          )
        ) : (
          <>
            {!query.data.directory_available && <p className="text-sm text-dt-burnt-orange">Employee details unavailable — showing Employee Codes only.</p>}
            <DataView caption={`Employees, ${periodLabel}`} rows={query.data.items} rowKey={(r) => r.emp_code}
              rowLabel={(r) => r.employee_name ?? r.emp_code} onRowClick={(r) => set({ open: r.emp_code, page: s.page })}
              sort={s.sort} onSort={(v) => set({ sort: v })}
              columns={[
                { key: "emp", header: "Employee", sort: "employee", cell: (r) => <Person photo={r.has_photo} name={r.employee_name} code={r.emp_code} meta={r.department ?? undefined} /> },
                { key: "status", header: "Status", cell: (r) => <StatusBadge r={r} /> },
                { key: "id", header: "Identity", minWidth: "xl", cell: (r) => <IdentityBadge cls={r.identity_class} /> },
                { key: "last", header: "Last activity", sort: "last_activity", minWidth: "lg", cell: (r) => <span className="whitespace-nowrap tabular-nums">{lastActivity(r)}</span> },
                { key: "days", header: "Activity days", sort: "activity_days", align: "right", cell: (r) => r.activity_days },
                { key: "events", header: "Events", sort: "events", align: "right", cell: (r) => r.events },
                { key: "flags", header: "Review flags", sort: "review_flags", align: "right",
                  cell: (r) => r.review_flags ? <span className="font-semibold text-dt-warning">{r.review_flags}</span> : <span className="text-dt-text-secondary">0</span> },
              ]}
              card={(r) => (
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <Person photo={r.has_photo} name={r.employee_name} code={r.emp_code} meta={r.department ?? undefined} />
                    <StatusBadge r={r} />
                  </div>
                  <Facts cols={3} items={[["Activity days", fmtNum(r.activity_days)], ["Events", fmtNum(r.events)],
                    ["Review flags", r.review_flags ? <span key="f" className="font-semibold text-dt-warning">{r.review_flags}</span> : "0"]]} />
                  <p className="text-xs text-dt-text-secondary">Last activity: {lastActivity(r)}</p>
                </div>
              )} />
            <Pager page={page} pageSize={pageSize} total={query.data.total} onPage={paging.onPage} onPageSize={paging.onPageSize} busy={query.isFetching} noun="employee" />
          </>
        )}
      {s.open && <EmployeeProfile code={s.open} to={s.to} onClose={() => set({ open: "", page: s.page })} />}
    </div>
  );
}

export default function EmployeesPage() {
  return <SiteProvider><Suspense fallback={<SkeletonRows />}><EmployeesView /></Suspense></SiteProvider>;
}
