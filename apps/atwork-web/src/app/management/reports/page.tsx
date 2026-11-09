"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button, Card, EmptyState, FormField, LoadingState, PageHeader, Select, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import { DateRange, Notice, Page, Pager, QueryError, RequirePermission, TotalsCards } from "@/components/ui";
import { errorMessage, management, type ReportFilters } from "@/lib/api";
import { addDays, ALL_WORK_MODES, dateTime, longDate, localDate, shortDuration, WORK_MODE_LABEL } from "@/lib/format";
import { hasPermission, PERM, useAtworkScope } from "@/lib/atwork-scope";
import { useDisplay } from "@/lib/hooks";

const LIMIT = 25;
const EXPORTS = [["employee_summary", "Employee summary"], ["sessions", "Sessions"], ["missed_checkouts", "Missed check-outs"], ["corrections", "Correction requests"]] as const;

function Screen() {
  const { scope } = useAtworkScope();
  const { zone, format } = useDisplay();
  const [range, setRange] = useState(() => {
    const to = localDate(Date.now(), zone);
    return { from: addDays(to, -29), to };
  });
  const [mode, setMode] = useState("");
  const [offset, setOffset] = useState(0);
  const [report, setReport] = useState<string>("employee_summary");
  const [employee, setEmployee] = useState<{ id: number; name: string } | null>(null);
  const filters: ReportFilters = { date_from: range.from, date_to: range.to, work_mode: mode, user_id: employee ? String(employee.id) : undefined };
  const summary = useQuery({ queryKey: ["atwork", "report", filters, offset], queryFn: () => management.report({ ...filters, limit: LIMIT, offset }) });
  const missed = useQuery({ queryKey: ["atwork", "report-missed", filters], queryFn: () => management.missed(filters) });
  const corrections = useQuery({ queryKey: ["atwork", "report-corrections", range, employee?.id], queryFn: () => management.correctionReport({ date_from: range.from, date_to: range.to, user_id: filters.user_id }) });
  const download = useMutation({ mutationFn: (f: "csv" | "xlsx") => management.download(report, f, filters) });
  const d = summary.data;
  return (
    <>
      <PageHeader title="Reports" description="Operational working hours. These are not payroll figures." />
      <Card className="mb-6 flex flex-wrap items-end gap-4 p-4">
        <DateRange from={range.from} to={range.to} onApply={(from, to) => { setRange({ from, to }); setOffset(0); }} />
        <FormField label="Work mode" htmlFor="report-mode"><Select id="report-mode" value={mode} onChange={(e) => { setMode(e.target.value); setOffset(0); }}><option value="">All</option>{ALL_WORK_MODES.map((m) => <option key={m} value={m}>{WORK_MODE_LABEL[m]}</option>)}</Select></FormField>
      </Card>
      {hasPermission(scope, PERM.EXPORT) && (
        <Card className="mb-6 flex flex-wrap items-end gap-3 p-4">
          <FormField label="Export" htmlFor="export-report"><Select id="export-report" value={report} onChange={(e) => setReport(e.target.value)}>{EXPORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></FormField>
          <Button variant="secondary" loading={download.isPending && download.variables === "csv"} disabled={download.isPending} onClick={() => download.mutate("csv")}>Download CSV</Button>
          <Button variant="secondary" loading={download.isPending && download.variables === "xlsx"} disabled={download.isPending} onClick={() => download.mutate("xlsx")}>Download Excel</Button>
        </Card>
      )}
      {employee && <Notice tone="info" action={<Button size="sm" variant="secondary" onClick={() => { setEmployee(null); setOffset(0); }}>Show all employees</Button>}>Showing {employee.name} only.</Notice>}
      {download.isError && <Notice tone="error">{errorMessage(download.error)}</Notice>}
      {summary.isLoading ? <LoadingState /> : !d ? <QueryError error={summary.error} retry={() => summary.refetch()} /> : d.session_count === 0 ? <EmptyState title="No attendance in this range" /> : (
        <div className="space-y-6">
          <TotalsCards totals={d.totals} />
          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="p-5"><h2 className="text-base font-semibold">By work mode</h2><ul className="mt-3 space-y-2 text-sm">{d.by_work_mode.map((m) => <li key={m.work_mode} className="flex justify-between gap-3"><span>{WORK_MODE_LABEL[m.work_mode]}</span><span>Net {shortDuration(m.net_seconds)}</span></li>)}</ul></Card>
            <Card className="p-5"><h2 className="text-base font-semibold">Correction requests</h2>{corrections.data ? <ul className="mt-3 space-y-2 text-sm"><li className="flex justify-between"><span>Total</span><span>{corrections.data.total}</span></li>{Object.entries(corrections.data.by_status).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k.charAt(0) + k.slice(1).toLowerCase()}</span><span>{v}</span></li>)}</ul> : <p className="mt-3 text-sm text-dt-text-secondary">Not available.</p>}</Card>
          </div>
          <section><h2 className="mb-2 text-base font-semibold">Employee summaries</h2><Table><Thead><Tr><Th>Employee</Th><Th>Sessions</Th><Th>Gross</Th><Th>Break</Th><Th>Net</Th></Tr></Thead><tbody>{d.by_employee.map((e) => <Tr key={e.platform_user_id}><Td><button type="button" className="font-medium underline-offset-2 hover:underline" onClick={() => { setEmployee({ id: e.platform_user_id, name: e.employee_name }); setOffset(0); }}>{e.employee_name}</button></Td><Td>{e.session_count}</Td><Td>{shortDuration(e.totals.gross_seconds)}</Td><Td>{shortDuration(e.totals.break_seconds)}</Td><Td>{shortDuration(e.totals.net_seconds)}</Td></Tr>)}</tbody></Table><Pager total={d.employee_total} limit={LIMIT} offset={offset} onChange={setOffset} /></section>
          <section><h2 className="mb-2 text-base font-semibold">Daily working hours</h2><Table><Thead><Tr><Th>Date</Th><Th>Gross</Th><Th>Break</Th><Th>Net</Th></Tr></Thead><tbody>{d.by_day.map((x) => <Tr key={x.date}><Td>{longDate(x.date)}</Td><Td>{shortDuration(x.gross_seconds)}</Td><Td>{shortDuration(x.break_seconds)}</Td><Td>{shortDuration(x.net_seconds)}</Td></Tr>)}</tbody></Table></section>
        </div>
      )}
      {missed.data && missed.data.total > 0 && <section className="mt-6"><h2 className="mb-2 text-base font-semibold">Missed check-outs (over {missed.data.threshold_hours} hours)</h2><Table><Thead><Tr><Th>Employee</Th><Th>Check-in</Th><Th>Open for</Th></Tr></Thead><tbody>{missed.data.items.map((m) => <Tr key={m.session_id}><Td>{m.employee_name}</Td><Td>{dateTime(m.check_in_at, zone, format)}</Td><Td>{shortDuration(m.open_seconds)}</Td></Tr>)}</tbody></Table></section>}
    </>
  );
}

export default function ReportsPage() {
  return <Page><RequirePermission permission={[PERM.MANAGEMENT, PERM.REPORTS]} title="Report access required"><Screen /></RequirePermission></Page>;
}
