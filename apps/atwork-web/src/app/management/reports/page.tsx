"use client";

import Link from "next/link";
import React, { useState, useMemo, useCallback } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Button, Card, EmptyState, FormField, LoadingState, PageHeader, Select, StatusBadge,
  Table, Td, Th, Thead, Tr,
} from "@dijione/design-system";
import { DateRange, Notice, Page, Pager, QueryError, RequirePermission, TotalsCards } from "@/components/ui";
import { errorMessage, management, type ReportFilters, type SessionReportItem } from "@/lib/api";
import {
  addDays, ALL_WORK_MODES, dateTime, localDate, longDate, shortDuration, WORK_MODE_LABEL,
} from "@/lib/format";
import { hasPermission, PERM, useAtworkScope } from "@/lib/atwork-scope";
import { useDisplay } from "@/lib/hooks";

const LIMIT = 25;

type ReportType = "employee_summary" | "sessions" | "missed_checkouts" | "corrections";

const REPORT_TABS: { key: ReportType; label: string; description: string }[] = [
  { key: "employee_summary", label: "Employee Summary", description: "Review employee attendance, verified working hours and unverified sessions for the selected period." },
  { key: "sessions", label: "Sessions", description: "Inspect individual attendance sessions, work modes and durations for the selected period." },
  { key: "missed_checkouts", label: "Missed Check-outs", description: "Open sessions that have exceeded the missed check-out threshold and may need attention." },
  { key: "corrections", label: "Corrections", description: "Review correction requests submitted by employees during the selected period." },
];

// ─── Inline SVG bar chart ─────────────────────────────────────────────────────

function BarChart({ bars, height = 80 }: { bars: { label: string; value: number; tone?: "brand" | "warn" | "muted" }[]; height?: number }) {
  const max = Math.max(...bars.map((b) => b.value), 1);
  const fill = (tone?: string) =>
    tone === "brand" ? "#e05120" : tone === "warn" ? "#d97706" : "#94a3b8";
  return (
    <div aria-hidden className="mt-3 overflow-hidden">
      <svg viewBox={`0 0 ${bars.length * 40} ${height + 20}`} width="100%" height={height + 20} preserveAspectRatio="none">
        {bars.map((b, i) => {
          const barH = max > 0 ? (b.value / max) * height : 0;
          const x = i * 40 + 4;
          const y = height - barH;
          return (
            <g key={b.label}>
              <rect x={x} y={y} width={32} height={barH} rx={3} fill={fill(b.tone)} opacity={0.85} />
            </g>
          );
        })}
      </svg>
      <div className="flex gap-0.5 overflow-hidden" style={{ display: "grid", gridTemplateColumns: `repeat(${bars.length}, 1fr)` }}>
        {bars.map((b) => (
          <span key={b.label} className="truncate text-center text-xs text-dt-text-secondary" title={b.label}>{b.label}</span>
        ))}
      </div>
    </div>
  );
}

// ─── Stat pill ────────────────────────────────────────────────────────────────

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: "warn" | "ok" | "muted" }) {
  const color = tone === "warn" ? "text-dt-warning" : tone === "ok" ? "text-dt-success" : "text-dt-text-primary";
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-dt-text-secondary">{label}</span>
      <span className={`text-sm font-semibold ${color}`}>{value}</span>
    </div>
  );
}

// ─── Employee Summary tab ─────────────────────────────────────────────────────

type SortKey = "employee_name" | "session_count" | "net" | "gross" | "unverified";

function EmployeeSummaryTab({
  filters, offset, onOffset,
}: { filters: ReportFilters; offset: number; onOffset: (n: number) => void }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "employee_name", dir: "asc" });
  const [expanded, setExpanded] = useState<number | null>(null);
  const query = useQuery({
    queryKey: ["atwork", "report", filters, offset],
    queryFn: () => management.report({ ...filters, limit: LIMIT, offset }),
  });
  const d = query.data;

  const sorted = useMemo(() => {
    if (!d) return [];
    return [...d.by_employee].sort((a, b) => {
      let x = 0;
      if (sort.key === "employee_name") x = a.employee_name.localeCompare(b.employee_name);
      else if (sort.key === "session_count") x = a.session_count - b.session_count;
      else if (sort.key === "net") x = a.totals.net_seconds - b.totals.net_seconds;
      else if (sort.key === "gross") x = a.totals.gross_seconds - b.totals.gross_seconds;
      else if (sort.key === "unverified") x = (a.totals.provisional_seconds ?? 0) - (b.totals.provisional_seconds ?? 0);
      return sort.dir === "asc" ? x : -x;
    });
  }, [d, sort]);

  function toggleSort(key: SortKey) {
    setSort((s) => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  }

  function SortTh({ col, children }: { col: SortKey; children: React.ReactNode }) {
    const active = sort.key === col;
    return (
      <Th>
        <button
          type="button"
          className={`flex items-center gap-1 ${active ? "font-bold text-dt-burnt-orange" : ""}`}
          onClick={() => toggleSort(col)}
        >
          {children}
          <span aria-hidden className="text-xs">{active ? (sort.dir === "asc" ? "↑" : "↓") : "↕"}</span>
        </button>
      </Th>
    );
  }

  if (query.isLoading) return <LoadingState />;
  if (!d) return <QueryError error={query.error} retry={() => query.refetch()} />;
  if (d.session_count === 0) return <EmptyState title="No attendance in this range" />;

  const topEmployees = [...d.by_employee]
    .sort((a, b) => b.totals.net_seconds - a.totals.net_seconds)
    .slice(0, 8);

  return (
    <div className="space-y-6">
      <TotalsCards totals={d.totals} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="text-sm font-semibold">Net working hours by employee</h3>
          <BarChart
            bars={topEmployees.map((e) => ({
              label: e.employee_name.split(" ")[0],
              value: e.totals.net_seconds,
              tone: "brand",
            }))}
          />
        </Card>
        <Card className="p-5">
          <h3 className="text-sm font-semibold">By work mode</h3>
          <ul className="mt-3 space-y-2 text-sm">
            {d.by_work_mode.map((m) => (
              <li key={m.work_mode} className="flex justify-between gap-3">
                <span>{WORK_MODE_LABEL[m.work_mode]}</span>
                <span className="tabular-nums">Net {shortDuration(m.net_seconds)}</span>
              </li>
            ))}
          </ul>
          {d.by_work_mode.length > 1 && (
            <BarChart
              bars={d.by_work_mode.map((m) => ({ label: WORK_MODE_LABEL[m.work_mode].split(" ")[0], value: m.net_seconds, tone: "muted" }))}
            />
          )}
        </Card>
      </div>

      <section>
        <h3 className="mb-2 text-sm font-semibold">Employee summaries ({d.employee_total})</h3>
        <Table>
          <Thead>
            <Tr>
              <SortTh col="employee_name">Employee</SortTh>
              <SortTh col="session_count">Sessions</SortTh>
              <SortTh col="gross">Gross</SortTh>
              <Th>Break</Th>
              <SortTh col="net">Net</SortTh>
              <SortTh col="unverified">Unverified</SortTh>
            </Tr>
          </Thead>
          <tbody>
            {sorted.map((e) => (
              <React.Fragment key={e.platform_user_id}>
                <Tr>
                  <Td>
                    <button
                      type="button"
                      className="font-medium underline-offset-2 hover:underline"
                      onClick={() => setExpanded(expanded === e.platform_user_id ? null : e.platform_user_id)}
                    >
                      {e.employee_name}
                    </button>
                  </Td>
                  <Td>{e.session_count}</Td>
                  <Td>{shortDuration(e.totals.gross_seconds)}</Td>
                  <Td>{shortDuration(e.totals.break_seconds)}</Td>
                  <Td className="font-medium">{shortDuration(e.totals.net_seconds)}</Td>
                  <Td>
                    {(e.totals.provisional_seconds ?? 0) > 0
                      ? <span className="text-dt-warning">{shortDuration(e.totals.provisional_seconds ?? 0)}</span>
                      : "—"}
                  </Td>
                </Tr>
                {expanded === e.platform_user_id && (
                  <Tr>
                    <Td colSpan={6}>
                      <div className="rounded-lg bg-dt-surface-warm p-4">
                        <div className="flex flex-wrap gap-6">
                          <Stat label="Sessions" value={e.session_count} />
                          <Stat label="Gross" value={shortDuration(e.totals.gross_seconds)} />
                          <Stat label="Break" value={shortDuration(e.totals.break_seconds)} />
                          <Stat label="Net" value={shortDuration(e.totals.net_seconds)} tone="ok" />
                          {(e.totals.provisional_seconds ?? 0) > 0 && (
                            <Stat label="Unverified (not counted)" value={shortDuration(e.totals.provisional_seconds ?? 0)} tone="warn" />
                          )}
                        </div>
                        <div className="mt-3">
                          <Link
                            href={`/management/employees/${e.platform_user_id}`}
                            className="text-sm text-dt-burnt-orange underline-offset-2 hover:underline"
                          >
                            View full attendance history →
                          </Link>
                        </div>
                      </div>
                    </Td>
                  </Tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </Table>
        <Pager total={d.employee_total} limit={LIMIT} offset={offset} onChange={onOffset} />
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold">Daily working hours</h3>
        {d.by_day.length > 0 && (
          <BarChart
            height={60}
            bars={d.by_day.map((x) => ({ label: x.date.slice(5), value: x.net_seconds, tone: "brand" }))}
          />
        )}
        <Table>
          <Thead><Tr><Th>Date</Th><Th>Gross</Th><Th>Break</Th><Th>Net</Th><Th>Unverified</Th></Tr></Thead>
          <tbody>
            {d.by_day.map((x) => (
              <Tr key={x.date}>
                <Td>{longDate(x.date)}</Td>
                <Td>{shortDuration(x.gross_seconds)}</Td>
                <Td>{shortDuration(x.break_seconds)}</Td>
                <Td>{shortDuration(x.net_seconds)}</Td>
                <Td>{shortDuration(x.provisional_seconds ?? 0)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </section>
    </div>
  );
}

// ─── Sessions tab ─────────────────────────────────────────────────────────────

type SessionSortKey = "employee_name" | "check_in_at" | "work_mode" | "status" | "net";

function SessionsTab({ filters, offset, onOffset }: { filters: ReportFilters; offset: number; onOffset: (n: number) => void }) {
  const { zone, format } = useDisplay();
  const [sort, setSort] = useState<{ key: SessionSortKey; dir: "asc" | "desc" }>({ key: "check_in_at", dir: "desc" });
  const query = useQuery({
    queryKey: ["atwork", "report-sessions", filters, offset],
    queryFn: () => management.reportSessions({ ...filters, limit: LIMIT, offset }),
  });
  const d = query.data;

  const sorted = useMemo<SessionReportItem[]>(() => {
    if (!d) return [];
    return [...d.items].sort((a, b) => {
      let x = 0;
      if (sort.key === "employee_name") x = a.employee_name.localeCompare(b.employee_name);
      else if (sort.key === "check_in_at") x = a.session.check_in_at.localeCompare(b.session.check_in_at);
      else if (sort.key === "work_mode") x = a.session.work_mode.localeCompare(b.session.work_mode);
      else if (sort.key === "status") x = a.session.status.localeCompare(b.session.status);
      else if (sort.key === "net") x = a.period_totals.net_seconds - b.period_totals.net_seconds;
      return sort.dir === "asc" ? x : -x;
    });
  }, [d, sort]);

  function toggleSort(key: SessionSortKey) {
    setSort((s) => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" });
  }

  function SortTh({ col, children }: { col: SessionSortKey; children: React.ReactNode }) {
    const active = sort.key === col;
    return (
      <Th>
        <button
          type="button"
          className={`flex items-center gap-1 ${active ? "font-bold text-dt-burnt-orange" : ""}`}
          onClick={() => toggleSort(col)}
        >
          {children}
          <span aria-hidden className="text-xs">{active ? (sort.dir === "asc" ? "↑" : "↓") : "↕"}</span>
        </button>
      </Th>
    );
  }

  if (query.isLoading) return <LoadingState />;
  if (!d) return <QueryError error={query.error} retry={() => query.refetch()} />;
  if (d.total === 0) return <EmptyState title="No sessions in this range" />;

  const byStatus = sorted.reduce<Record<string, number>>((acc, i) => {
    acc[i.session.status] = (acc[i.session.status] ?? 0) + 1;
    return acc;
  }, {});

  const byMode = sorted.reduce<Record<string, number>>((acc, i) => {
    acc[i.session.work_mode] = (acc[i.session.work_mode] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="text-sm font-semibold">Sessions by status</h3>
          <ul className="mt-3 space-y-2 text-sm">
            {Object.entries(byStatus).map(([k, v]) => (
              <li key={k} className="flex justify-between gap-3">
                <span>{k.charAt(0) + k.slice(1).toLowerCase()}</span>
                <span className="tabular-nums">{v}</span>
              </li>
            ))}
          </ul>
          <BarChart
            bars={Object.entries(byStatus).map(([k, v]) => ({ label: k.slice(0, 4), value: v, tone: k === "OPEN" ? "warn" : "brand" }))}
          />
        </Card>
        <Card className="p-5">
          <h3 className="text-sm font-semibold">Sessions by work mode</h3>
          <ul className="mt-3 space-y-2 text-sm">
            {Object.entries(byMode).map(([k, v]) => (
              <li key={k} className="flex justify-between gap-3">
                <span>{WORK_MODE_LABEL[k as keyof typeof WORK_MODE_LABEL] ?? k}</span>
                <span className="tabular-nums">{v}</span>
              </li>
            ))}
          </ul>
          <BarChart
            bars={Object.entries(byMode).map(([k, v]) => ({ label: (WORK_MODE_LABEL[k as keyof typeof WORK_MODE_LABEL] ?? k).split(" ")[0], value: v, tone: "muted" }))}
          />
        </Card>
      </div>

      <section>
        <h3 className="mb-2 text-sm font-semibold">Sessions ({d.total})</h3>
        <Table>
          <Thead>
            <Tr>
              <SortTh col="employee_name">Employee</SortTh>
              <SortTh col="check_in_at">Check-in</SortTh>
              <Th>Check-out</Th>
              <SortTh col="work_mode">Mode</SortTh>
              <SortTh col="status">Status</SortTh>
              <SortTh col="net">Net</SortTh>
              <Th>Gross</Th>
              <Th></Th>
            </Tr>
          </Thead>
          <tbody>
            {sorted.map((item) => {
              const s = item.session;
              return (
                <Tr key={s.id}>
                  <Td className="font-medium">{item.employee_name}</Td>
                  <Td>{dateTime(s.check_in_at, zone, format)}</Td>
                  <Td>{s.check_out_at ? dateTime(s.check_out_at, zone, format) : <span className="text-dt-warning">In progress</span>}</Td>
                  <Td>{WORK_MODE_LABEL[s.work_mode]}</Td>
                  <Td>
                    <StatusBadge status={s.status === "OPEN" ? "ACTIVE" : "COMPLETED"} label={s.status === "OPEN" ? "Active" : "Completed"} />
                    {s.unverified && <span className="ml-1"><StatusBadge status="PENDING" label="Unverified" /></span>}
                  </Td>
                  <Td className="tabular-nums">
                    {s.unverified
                      ? <span className="text-dt-warning">—</span>
                      : shortDuration(item.period_totals.net_seconds)}
                  </Td>
                  <Td className="tabular-nums">{s.unverified ? shortDuration(s.elapsed_seconds ?? 0) : shortDuration(item.period_totals.gross_seconds)}</Td>
                  <Td>
                    <Link href={`/management/sessions/${s.id}`} className="text-xs text-dt-burnt-orange underline-offset-2 hover:underline">View</Link>
                  </Td>
                </Tr>
              );
            })}
          </tbody>
        </Table>
        <Pager total={d.total} limit={LIMIT} offset={offset} onChange={onOffset} />
      </section>
    </div>
  );
}

// ─── Missed check-outs tab ────────────────────────────────────────────────────

function MissedCheckoutsTab({ filters }: { filters: ReportFilters }) {
  const { zone, format } = useDisplay();
  const query = useQuery({
    queryKey: ["atwork", "report-missed", filters],
    queryFn: () => management.missed(filters),
  });
  const d = query.data;

  if (query.isLoading) return <LoadingState />;
  if (!d) return <QueryError error={query.error} retry={() => query.refetch()} />;
  if (d.total === 0) return <EmptyState title="No missed check-outs in this range" description={`No open sessions past the ${d.threshold_hours}-hour threshold.`} />;

  const topOverdue = [...d.items].sort((a, b) => b.open_seconds - a.open_seconds).slice(0, 8);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="text-sm font-semibold">Open overdue sessions</h3>
          <div className="mt-3 flex flex-wrap gap-6">
            <Stat label="Total overdue" value={d.total} tone="warn" />
            <Stat label="Threshold" value={`${d.threshold_hours} hours`} />
          </div>
        </Card>
        <Card className="p-5">
          <h3 className="text-sm font-semibold">Unverified duration by employee</h3>
          <BarChart
            bars={topOverdue.map((m) => ({ label: m.employee_name.split(" ")[0], value: m.open_seconds, tone: "warn" }))}
          />
        </Card>
      </div>

      <section>
        <h3 className="mb-2 text-sm font-semibold">Missed check-outs (over {d.threshold_hours} hours)</h3>
        <Table>
          <Thead><Tr><Th>Employee</Th><Th>Mode</Th><Th>Check-in</Th><Th>Open for</Th><Th>Break open</Th><Th></Th></Tr></Thead>
          <tbody>
            {d.items.map((m) => (
              <Tr key={m.session_id}>
                <Td className="font-medium">{m.employee_name}</Td>
                <Td>{WORK_MODE_LABEL[m.work_mode]}</Td>
                <Td>{dateTime(m.check_in_at, zone, format)}</Td>
                <Td><span className="text-dt-warning font-medium">{shortDuration(m.open_seconds)}</span></Td>
                <Td>{m.break_open ? <StatusBadge status="PENDING" label="Yes" /> : "No"}</Td>
                <Td>
                  <Link href={`/management/sessions/${m.session_id}`} className="text-xs text-dt-burnt-orange underline-offset-2 hover:underline">View</Link>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </section>
    </div>
  );
}

// ─── Corrections tab ──────────────────────────────────────────────────────────

function CorrectionsTab({ filters, offset, onOffset }: { filters: ReportFilters; offset: number; onOffset: (n: number) => void }) {
  const { zone, format } = useDisplay();
  const [statusFilter, setStatusFilter] = useState("");
  const query = useQuery({
    queryKey: ["atwork", "report-corrections-preview", filters, statusFilter, offset],
    queryFn: () => management.corrections({ status: statusFilter || undefined, limit: LIMIT, offset }),
  });
  const statsQuery = useQuery({
    queryKey: ["atwork", "report-corrections", filters],
    queryFn: () => management.correctionReport({ date_from: filters.date_from, date_to: filters.date_to, user_id: filters.user_id }),
  });
  const d = query.data;
  const stats = statsQuery.data;

  if (query.isLoading) return <LoadingState />;
  if (!d) return <QueryError error={query.error} retry={() => query.refetch()} />;

  const statusEntries = stats ? Object.entries(stats.by_status).sort((a, b) => b[1] - a[1]) : [];

  return (
    <div className="space-y-6">
      {stats && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="p-5">
            <h3 className="text-sm font-semibold">Corrections by status</h3>
            <ul className="mt-3 space-y-2 text-sm">
              {statusEntries.map(([k, v]) => (
                <li key={k} className="flex justify-between gap-3">
                  <span>{k.charAt(0) + k.slice(1).toLowerCase()}</span>
                  <span className="tabular-nums">{v}</span>
                </li>
              ))}
            </ul>
            <BarChart
              bars={statusEntries.map(([k, v]) => ({
                label: k.slice(0, 5),
                value: v,
                tone: k === "PENDING" ? "warn" : k === "APPROVED" ? "brand" : "muted",
              }))}
            />
          </Card>
          <Card className="p-5">
            <h3 className="text-sm font-semibold">Summary</h3>
            <div className="mt-3 flex flex-wrap gap-6">
              <Stat label="Total requests" value={stats.total} />
              {stats.by_status["PENDING"] ? <Stat label="Pending" value={stats.by_status["PENDING"]} tone="warn" /> : null}
              {stats.by_status["APPROVED"] ? <Stat label="Approved" value={stats.by_status["APPROVED"]} tone="ok" /> : null}
            </div>
          </Card>
        </div>
      )}

      <div className="mb-4 max-w-xs">
        <FormField label="Status" htmlFor="corrections-status">
          <Select id="corrections-status" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); onOffset(0); }}>
            <option value="">All</option>
            <option value="PENDING">Pending</option>
            <option value="APPROVED">Approved</option>
            <option value="REJECTED">Rejected</option>
            <option value="WITHDRAWN">Withdrawn</option>
          </Select>
        </FormField>
      </div>

      {d.items.length === 0 ? (
        <EmptyState title="No corrections match" />
      ) : (
        <section>
          <h3 className="mb-2 text-sm font-semibold">Correction requests ({d.total})</h3>
          <Table>
            <Thead><Tr><Th>Employee</Th><Th>Type</Th><Th>Requested</Th><Th>Status</Th><Th>Reviewer</Th><Th></Th></Tr></Thead>
            <tbody>
              {d.items.map((c) => (
                <Tr key={c.id}>
                  <Td className="font-medium">{c.employee_name}</Td>
                  <Td>{c.kind === "AMEND" ? "Session correction" : "Missing session"}</Td>
                  <Td>{dateTime(c.created_at, zone, format)}</Td>
                  <Td><StatusBadge status={c.status} /></Td>
                  <Td>{c.reviewer_name ?? "—"}</Td>
                  <Td>
                    <Link href={`/management/corrections/${c.id}`} className="text-xs text-dt-burnt-orange underline-offset-2 hover:underline">Review</Link>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
          <Pager total={d.total} limit={LIMIT} offset={offset} onChange={onOffset} />
        </section>
      )}
    </div>
  );
}

// ─── Main screen ──────────────────────────────────────────────────────────────

function Screen() {
  const { scope } = useAtworkScope();
  const { zone } = useDisplay();
  const [activeTab, setActiveTab] = useState<ReportType>("employee_summary");
  const [range, setRange] = useState(() => {
    const to = localDate(Date.now(), zone);
    return { from: addDays(to, -29), to };
  });
  const [mode, setMode] = useState("");
  const [selectedEmployee, setSelectedEmployee] = useState<{ id: number; name: string } | null>(null);
  const [offset, setOffset] = useState(0);

  const filters: ReportFilters = {
    date_from: range.from,
    date_to: range.to,
    work_mode: mode || undefined,
    user_id: selectedEmployee ? String(selectedEmployee.id) : undefined,
  };

  const download = useMutation({ mutationFn: (f: "csv" | "xlsx") => management.download(activeTab, f, filters) });

  const activeTabInfo = REPORT_TABS.find((t) => t.key === activeTab)!;

  const handleTabChange = useCallback((key: ReportType) => {
    setActiveTab(key);
    setOffset(0);
  }, []);

  const handleFilterApply = useCallback((from: string, to: string) => {
    setRange({ from, to });
    setOffset(0);
  }, []);

  return (
    <>
      <PageHeader title="Reports" description="Operational working hours. These are not payroll figures." />

      {/* Global filters */}
      <Card className="mb-6 flex flex-wrap items-end gap-4 p-4">
        <DateRange from={range.from} to={range.to} onApply={handleFilterApply} />
        <FormField label="Work mode" htmlFor="report-mode">
          <Select id="report-mode" value={mode} onChange={(e) => { setMode(e.target.value); setOffset(0); }}>
            <option value="">All</option>
            {ALL_WORK_MODES.map((m) => <option key={m} value={m}>{WORK_MODE_LABEL[m]}</option>)}
          </Select>
        </FormField>
        {selectedEmployee && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-dt-text-secondary">Employee: <strong>{selectedEmployee.name}</strong></span>
            <Button size="sm" variant="secondary" onClick={() => { setSelectedEmployee(null); setOffset(0); }}>Clear</Button>
          </div>
        )}
      </Card>

      {/* Tab navigation */}
      <div className="mb-6 flex flex-wrap gap-1 rounded-xl bg-dt-surface-warm p-1" role="tablist">
        {REPORT_TABS.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            onClick={() => handleTabChange(tab.key)}
            className={[
              "rounded-lg px-4 py-2 text-sm font-medium transition-colors",
              activeTab === tab.key
                ? "bg-dt-orange text-white shadow-sm"
                : "text-dt-text-secondary hover:text-dt-text-primary",
            ].join(" ")}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Report header + export */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">{activeTabInfo.label}</h2>
          <p className="mt-1 text-sm text-dt-text-secondary">{activeTabInfo.description}</p>
        </div>
        {hasPermission(scope, PERM.EXPORT) && (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              loading={download.isPending && download.variables === "csv"}
              disabled={download.isPending}
              onClick={() => download.mutate("csv")}
            >
              Download CSV
            </Button>
            <Button
              variant="secondary"
              loading={download.isPending && download.variables === "xlsx"}
              disabled={download.isPending}
              onClick={() => download.mutate("xlsx")}
            >
              Download Excel
            </Button>
          </div>
        )}
      </div>

      {download.isError && <Notice tone="error">{errorMessage(download.error)}</Notice>}

      {/* Report preview */}
      <div role="tabpanel">
        {activeTab === "employee_summary" && (
          <EmployeeSummaryTab filters={filters} offset={offset} onOffset={setOffset} />
        )}
        {activeTab === "sessions" && (
          <SessionsTab filters={filters} offset={offset} onOffset={setOffset} />
        )}
        {activeTab === "missed_checkouts" && (
          <MissedCheckoutsTab filters={filters} />
        )}
        {activeTab === "corrections" && (
          <CorrectionsTab filters={filters} offset={offset} onOffset={setOffset} />
        )}
      </div>
    </>
  );
}

export default function ReportsPage() {
  return (
    <Page>
      <RequirePermission permission={[PERM.MANAGEMENT, PERM.REPORTS]} title="Report access required">
        <Screen />
      </RequirePermission>
    </Page>
  );
}
