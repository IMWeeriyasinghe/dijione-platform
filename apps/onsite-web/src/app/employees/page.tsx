"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, EmptyState, ErrorState, LoadingState, PageHeader, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import { Users, X } from "lucide-react";
import { ColumnChart } from "@/components/charts";
import { ExportButton } from "@/components/ExportButton";
import { FreshnessIndicator } from "@/components/FreshnessIndicator";
import { DateInput, DepartmentSelect, FilterRow, IdentitySelect, Pager, SelectFilter, SiteSelect, TextFilter } from "@/components/FilterBar";
import { EmployeeCell, FlagChips, IdentityBadge } from "@/components/FlagChips";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { liveQuery } from "@/lib/live-refresh";
import { getEmployee, getEmployees } from "@/lib/dashboard";
import { addDays, formatSpan, localTime } from "@/lib/flags";

function EmployeeDrawer({ code, from, to, onClose }: { code: string; from: string; to: string; onClose: () => void }) {
  const { site } = useSite();
  const query = useQuery({
    queryKey: ["onsite-employee", site.site_id, code, from, to],
    queryFn: () => getEmployee(code, { site_id: site.site_id, date_from: from, date_to: to }),
    ...liveQuery,
  });
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" role="dialog" aria-modal="true" aria-label={`Activity for ${code}`}>
      <div className="h-full w-full max-w-2xl overflow-y-auto bg-dt-background p-6 shadow-xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-dt-text-primary">{query.data?.profile.employee_name ?? "Unmatched code"}</h2>
            <p className="font-mono text-sm text-dt-text-secondary">{code}</p>
            {query.data && (
              <p className="mt-1 text-sm text-dt-text-secondary">
                {[query.data.profile.department, query.data.profile.job_title, query.data.profile.employment_status].filter(Boolean).join(" · ") || "No Workforce Directory match"}
              </p>
            )}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close"><X className="size-4" /></Button>
        </div>
        {query.isLoading ? <LoadingState label="Loading activity…" /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> : (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-3 text-sm text-dt-text-secondary">
              <IdentityBadge cls={query.data.profile.identity_class} />
              <span>{query.data.summary.activity_days} activity days</span>
              <span>{query.data.summary.events} activity events</span>
              <span>{query.data.summary.review_flags} review flags</span>
            </div>
            {query.data.days.length > 0 && (
              <ColumnChart
                label="Activity count per day"
                valueLabel="events"
                data={[...query.data.days].reverse().map((d) => ({ key: d.local_date, value: d.punch_count }))}
                xLabel={(d) => d.slice(5)}
              />
            )}
            {query.data.days.length === 0 ? <p className="text-sm text-dt-text-secondary">No activity recorded in this range.</p> : (
              <Table>
                <Thead><Tr><Th>Date</Th><Th>First</Th><Th>Latest</Th><Th>Count</Th><Th>Span</Th><Th>Terminals</Th><Th>Review</Th></Tr></Thead>
                <tbody>
                  {query.data.days.map((d) => (
                    <Tr key={d.local_date}>
                      <Td className="whitespace-nowrap">{d.local_date}</Td>
                      <Td>{localTime(d.first_activity_local)}</Td>
                      <Td>{localTime(d.latest_activity_local)}</Td>
                      <Td className="tabular-nums">{d.punch_count}</Td>
                      <Td>{formatSpan(d.span_minutes)}</Td>
                      <Td>{d.terminal_names.join(", ") || "—"}</Td>
                      <Td><FlagChips flags={d.flags} /></Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            )}
            {query.data.events.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-semibold text-dt-text-primary">Activity timeline</h3>
                <ol className="space-y-1 border-l border-dt-border pl-4 text-sm">
                  {query.data.events.slice(0, 200).map((e, i) => (
                    <li key={e.event_id ?? `${e.local_time}-${i}`} className="text-dt-text-secondary">
                      <span className="text-dt-text-primary">{e.local_date} {localTime(e.local_time)}</span> · {e.terminal ?? "Unknown terminal"}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function EmployeesView() {
  const { site } = useSite();
  const end0 = site.last_activity_date ?? site.today;
  const [from, setFrom] = useState(addDays(end0, -29));
  const [to, setTo] = useState(end0);
  const [q, setQ] = useState("");
  const [empCode, setEmpCode] = useState("");
  const [department, setDepartment] = useState("");
  const [identity, setIdentity] = useState("");
  const [status, setStatus] = useState("");
  const [activity, setActivity] = useState("with_activity");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const filters = { site_id: site.site_id, date_from: from, date_to: to, q: q || undefined, emp_code: empCode.trim() || undefined,
    department: department || undefined, identity_class: identity || undefined, employment_status: status || undefined,
    activity: activity || undefined };
  const params = { ...filters, page, page_size: 50 };
  const query = useQuery({ queryKey: ["onsite-employees", params], queryFn: () => getEmployees(params), ...liveQuery });
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1); };

  return (
    <div>
      <PageHeader title="Employees" description="Attendance activity per employee. Employees are matched by exact Employee Number."
        action={<ExportButton path="employees" params={filters} />} />
      <FreshnessIndicator siteId={site.site_id} queries={[query]} />
      <FilterRow>
        <SiteSelect />
        <DateInput label="From" value={from} onChange={reset(setFrom)} />
        <DateInput label="To" value={to} onChange={reset(setTo)} />
      </FilterRow>
      <FilterRow>
        <TextFilter label="Search employee or code" value={q} onChange={reset(setQ)} />
        <TextFilter label="Employee Number" value={empCode} onChange={reset(setEmpCode)} />
        <DepartmentSelect value={department} onChange={reset(setDepartment)} />
        <IdentitySelect value={identity} onChange={reset(setIdentity)} />
        <SelectFilter label="Employment status" value={status} onChange={reset(setStatus)}
          options={[{ value: "", label: "Any status" }, { value: "Active", label: "Active" }, { value: "Inactive", label: "Inactive" }]} />
        <SelectFilter label="Activity" value={activity} onChange={reset(setActivity)}
          options={[{ value: "with_activity", label: "Activity recorded" }, { value: "no_activity", label: "No activity recorded" }, { value: "", label: "Everyone" }]} />
      </FilterRow>
      {query.isLoading ? <LoadingState label="Loading employees…" /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> :
        query.data.total === 0 ? <EmptyState icon={Users} title="No employees match" description="Try a different date range or filters." /> : (
          <>
            {!query.data.directory_available && <p className="mb-2 text-sm text-dt-burnt-orange">Employee details unavailable — showing attendance codes only.</p>}
            <Table>
              <Thead><Tr><Th>Employee</Th><Th>Department</Th><Th>Status</Th><Th>Last activity</Th><Th>Activity days</Th><Th>Events</Th><Th>Review flags</Th></Tr></Thead>
              <tbody>
                {query.data.items.map((r) => (
                  <Tr key={r.emp_code} className="cursor-pointer hover:bg-dt-surface-warm" onClick={() => setSelected(r.emp_code)}>
                    <Td><EmployeeCell name={r.employee_name} code={r.emp_code} /></Td>
                    <Td>{r.department ?? "—"}</Td>
                    <Td>{r.employment_status ?? (r.in_directory ? "—" : "Not in directory")}</Td>
                    <Td className="whitespace-nowrap">{r.last_activity_local ? `${r.last_activity_local.slice(0, 10)} ${localTime(r.last_activity_local)}` : "—"}</Td>
                    <Td className="tabular-nums">{r.activity_days}</Td>
                    <Td className="tabular-nums">{r.events}</Td>
                    <Td className="tabular-nums">{r.review_flags}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
            <Pager page={page} pageSize={50} total={query.data.total} onPage={setPage} />
          </>
        )}
      {selected && <EmployeeDrawer code={selected} from={from} to={to} onClose={() => setSelected(null)} />}
    </div>
  );
}

export default function EmployeesPage() {
  return <SiteProvider><EmployeesView /></SiteProvider>;
}
