"use client";

import { Suspense, useState } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Button, ErrorState, MetricCard } from "@dijione/design-system";
import { CircleAlert, CircleCheck, Fingerprint, Upload, Users } from "lucide-react";
import { AdminOnly } from "@/components/AdminOnly";
import { DataView, Facts } from "@/components/DataView";
import { SearchField, SelectField, SiteSelect } from "@/components/FilterBar";
import { buttonClass, cx, InlineAlert, PageTop, Pager, Panel, SkeletonRows } from "@/components/kit";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { ToneBadge } from "@/components/ToneBadge";
import {
  CloseDialog, CodeDialog, CorrectDialog, HistoryDialog, MapDialog, ReassignDialog, RejectDialog, WithdrawDialog,
} from "@/components/identity/dialogs";
import { ID_LABELS } from "@/lib/format";
import {
  downloadIdentityList, errorDetail, getConflicts, getMappings, getReadiness, getUnmapped, importMappings,
  WARNING_LABEL, type ImportResult, type Mapping, type Rejection, type UnmappedRow,
} from "@/lib/identity";
import { hasPermission, PERM, useOnsiteScope } from "@/lib/onsite-scope";
import { fmtNum, normalizePeriod, presetPeriod } from "@/lib/period";
import { CoverageDashboard } from "@/components/identity/CoverageDashboard";
import { useUrlState } from "@/lib/url-state";

type Tab = "overview" | "readiness" | "unmapped" | "mappings" | "conflicts" | "import";
const TABS: [Tab, string][] = [
  ["overview", "Overview"], ["readiness", "Readiness"], ["unmapped", "Unmapped IDs"], ["mappings", "Mappings"],
  ["conflicts", "Conflicts & history"], ["import", "Import"],
];

type DialogState =
  | { kind: "map"; code?: string } | { kind: "reject"; code: string } | { kind: "code"; code: string }
  | { kind: "close" | "correct" | "reassign"; mapping: Mapping } | { kind: "history"; id: number }
  | { kind: "withdraw"; rejection: Rejection } | null;

function IdentityManagement() {
  const { site } = useSite();
  const { scope } = useOnsiteScope();
  const canManage = hasPermission(scope, PERM.IDENTITY_MANAGE);
  const [s, set] = useUrlState({ tab: "overview", q: "", status: "VERIFIED", mq: "", from: "", to: "" });
  const tab = (TABS.some(([t]) => t === s.tab) ? s.tab : "overview") as Tab;
  const period = s.from && s.to ? normalizePeriod({ from: s.from, to: s.to }) : presetPeriod("30d", site.today);
  const [dialog, setDialog] = useState<DialogState>(null);
  const close = () => setDialog(null);

  return (
    <div className="space-y-4">
      <PageTop title="Identity Management"
        description="Verified links between ZKBioTime IDs and BambooHR team members. Attendance is attributed only inside an administrator-verified ownership period — never by matching numbers or names."
        actions={canManage ? <Button onClick={() => setDialog({ kind: "map" })}>Map ZKBioTime ID</Button> : undefined}>
        <SiteSelect />
      </PageTop>
      {!canManage && <InlineAlert tone="info">Read-only: changing mappings requires the Manage Identity Mappings permission.</InlineAlert>}

      <div role="tablist" aria-label="Identity Management sections" className="flex flex-wrap gap-1">
        {TABS.map(([t, label]) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => set({ tab: t })}
            className={cx("min-h-9 rounded-md px-3 text-sm font-medium", tab === t ? "bg-dt-cream text-dt-burnt-orange" : "text-dt-text-secondary hover:bg-dt-surface-warm")}>
            {label}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === "overview" && (
          <CoverageDashboard siteId={site.site_id} siteName={site.name} today={site.today} period={period}
            onPeriod={(p) => set({ from: p.from, to: p.to })} canManage={canManage}
            onMap={(code) => setDialog({ kind: "map", code })}
            onInvestigate={(code) => set({ tab: "unmapped", q: code })} />
        )}
        {tab === "readiness" && <ReadinessTab siteId={site.site_id} />}
        {tab === "unmapped" && <UnmappedTab siteId={site.site_id} q={s.q} setQ={(q) => set({ q })} canManage={canManage} open={setDialog} />}
        {tab === "mappings" && <MappingsTab siteId={site.site_id} status={s.status} q={s.mq} set={set} canManage={canManage} open={setDialog} />}
        {tab === "conflicts" && <ConflictsTab siteId={site.site_id} canManage={canManage} open={setDialog} />}
        {tab === "import" && (canManage ? <ImportTab /> : <InlineAlert tone="info">Importing requires the Manage Identity Mappings permission.</InlineAlert>)}
      </div>

      {dialog?.kind === "map" && <MapDialog siteId={site.site_id} code={dialog.code} onClose={close} />}
      {dialog?.kind === "reject" && <RejectDialog siteId={site.site_id} code={dialog.code} onClose={close} />}
      {dialog?.kind === "code" && <CodeDialog siteId={site.site_id} code={dialog.code} onClose={close} />}
      {dialog?.kind === "close" && <CloseDialog mapping={dialog.mapping} onClose={close} />}
      {dialog?.kind === "correct" && <CorrectDialog mapping={dialog.mapping} onClose={close} />}
      {dialog?.kind === "reassign" && <ReassignDialog mapping={dialog.mapping} onClose={close} />}
      {dialog?.kind === "history" && <HistoryDialog mappingId={dialog.id} onClose={close} />}
      {dialog?.kind === "withdraw" && <WithdrawDialog rejection={dialog.rejection} onClose={close} />}
    </div>
  );
}

/* ---------------------------------------------------------------- readiness */

function ReadinessTab({ siteId }: { siteId: string }) {
  const q = useQuery({ queryKey: ["onsite-identity", "readiness", siteId], queryFn: () => getReadiness({ site_id: siteId, days: 30 }) });
  if (q.isLoading) return <SkeletonRows label="Loading readiness…" />;
  if (!q.data) return <ErrorState onRetry={() => q.refetch()} />;
  const r = q.data;
  const c = r.unresolved_conflicts;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard label="Identified punches" value={r.identified_punch_pct === null ? "—" : `${r.identified_punch_pct}%`} icon={CircleCheck} tone="brand" />
        <MetricCard label="Identified team members" value={fmtNum(r.identified_employees)} icon={Users} tone="neutral" />
        <MetricCard label="Unmapped ZKBioTime IDs" value={fmtNum(r.unmapped_codes)} icon={Fingerprint} tone="neutral" />
        <MetricCard label="Unresolved conflicts" value={fmtNum(c.conflict_days + c.overlapping_mappings + c.ambiguous_reassignment_days)} icon={CircleAlert}
          tone="neutral" />
      </div>
      <p className="text-sm text-dt-text-secondary">
        Last {r.window_days} days ({r.date_from} – {r.date_to}): {fmtNum(r.identified_punches)} of {fmtNum(r.total_punches)} punches attributed ·{" "}
        {fmtNum(r.active_codes)} active IDs · {fmtNum(r.unmapped_punches)} unmapped punches · {fmtNum(r.verified_mappings)} verified mappings ·{" "}
        {r.mappings_without_evidence} without evidence · directory {r.directory_available ? "available" : "unavailable"}.
      </p>
      <InlineAlert tone="info">These figures inform the production decision; the threshold is approved separately by the owner with HR/IT. Nothing here is automatic.</InlineAlert>
      <Panel title="High-volume outstanding IDs" subtitle="Top unmapped ZKBioTime IDs by punches in the window, with their disposition">
        {r.high_volume_outstanding_codes.length === 0 ? <p className="text-sm text-dt-text-secondary">No unmapped activity in the window.</p> : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-dt-text-secondary"><th>{ID_LABELS.zk}</th><th className="text-right">Unmapped punches</th><th>Disposition</th></tr></thead>
            <tbody>{r.high_volume_outstanding_codes.map((x) => (
              <tr key={x.zk_emp_code} className="border-t border-dt-border"><td className="font-mono">{x.zk_emp_code}</td>
                <td className="text-right tabular-nums">{fmtNum(x.unmapped_events)}</td>
                <td><ToneBadge tone={x.disposition === "undispositioned" ? "warning" : "neutral"}>{x.disposition}</ToneBadge></td></tr>
            ))}</tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

/* ----------------------------------------------------------------- unmapped */

function UnmappedTab({ siteId, q, setQ, canManage, open }: {
  siteId: string; q: string; setQ: (v: string) => void; canManage: boolean; open: (d: DialogState) => void;
}) {
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [exportError, setExportError] = useState(false);
  const params = { site_id: siteId, q: q || undefined, page, page_size: size };
  const query = useQuery({ queryKey: ["onsite-identity", "unmapped", params], queryFn: () => getUnmapped(params), placeholderData: keepPreviousData });
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="max-w-sm flex-1"><SearchField label={`Search ${ID_LABELS.zk}`} value={q} onChange={(v) => { setQ(v); setPage(1); }} /></div>
        <Button variant="secondary" onClick={async () => { setExportError(false); try { await downloadIdentityList("unmapped", { site_id: siteId }); } catch { setExportError(true); } }}>Export CSV</Button>
      </div>
      {exportError && <p className="text-sm text-dt-danger">Export failed. Please try again.</p>}
      <p className="text-sm text-dt-text-secondary">IDs with attendance that is not covered by a verified mapping on at least one day. Their punches are excluded from all attendance views and exports until verified.</p>
      {query.isLoading ? <SkeletonRows /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> : (
        <>
          <DataView<UnmappedRow> caption="Unmapped ZKBioTime IDs" rows={query.data.items} rowKey={(r) => `${r.site_id}:${r.zk_emp_code}`}
            columns={[
              { key: "id", header: ID_LABELS.zk, cell: (r) => <span className="font-mono font-medium">{r.zk_emp_code}</span> },
              { key: "first", header: "First attendance", minWidth: "lg", cell: (r) => r.first_seen },
              { key: "last", header: "Latest attendance", cell: (r) => r.last_seen },
              { key: "events", header: "Unmapped punches", align: "right", cell: (r) => <span className="tabular-nums">{fmtNum(r.unmapped_events)} / {fmtNum(r.event_count)}</span> },
              { key: "status", header: ID_LABELS.mapping, cell: (r) => <ToneBadge tone={r.mapped_today ? "warning" : "danger"}>{r.mapped_today ? "Partly verified" : "Unmapped"}</ToneBadge> },
              { key: "hint", header: "Unverified hint", minWidth: "xl", cell: (r) => <Hints r={r} /> },
              { key: "act", header: "Actions", cell: (r) => <UnmappedActions r={r} canManage={canManage} open={open} /> },
            ]}
            card={(r) => (
              <div className="space-y-2">
                <div className="flex justify-between"><span className="font-mono font-medium">{r.zk_emp_code}</span>
                  <ToneBadge tone={r.mapped_today ? "warning" : "danger"}>{r.mapped_today ? "Partly verified" : "Unmapped"}</ToneBadge></div>
                <Facts cols={3} items={[["Unmapped punches", fmtNum(r.unmapped_events)], ["First", r.first_seen], ["Latest", r.last_seen]]} />
                <Hints r={r} />
                <UnmappedActions r={r} canManage={canManage} open={open} />
              </div>
            )} />
          <Pager page={page} pageSize={size} total={query.data.total} noun="ID" busy={query.isFetching} onPage={setPage}
            onPageSize={(n) => { setSize(n); setPage(1); }} />
        </>
      )}
    </div>
  );
}

function Hints({ r }: { r: UnmappedRow }) {
  if (!r.hint_employee_number_matches.length) return <span className="text-xs text-dt-text-secondary">—</span>;
  return (
    <span className="flex flex-wrap gap-1" title="An EMP Number equals this ID. This is NOT evidence and is never applied automatically.">
      {r.hint_employee_number_matches.map((h) => (
        <span key={h.bamboohr_id} className="rounded border border-dashed border-dt-border px-1.5 py-0.5 text-xs text-dt-text-secondary">
          Unverified: {h.display_name ?? h.bamboohr_id}
        </span>
      ))}
    </span>
  );
}

function UnmappedActions({ r, canManage, open }: { r: UnmappedRow; canManage: boolean; open: (d: DialogState) => void }) {
  return (
    <span className="flex flex-wrap gap-1">
      <button type="button" className={buttonClass("ghost")} onClick={() => open({ kind: "code", code: r.zk_emp_code })}>Investigate</button>
      {canManage && <button type="button" className={buttonClass("secondary")} onClick={() => open({ kind: "map", code: r.zk_emp_code })}>Map…</button>}
      {canManage && <button type="button" className={buttonClass("ghost")} onClick={() => open({ kind: "reject", code: r.zk_emp_code })}>Not this person…</button>}
    </span>
  );
}

/* ----------------------------------------------------------------- mappings */

function MappingsTab({ siteId, status, q, set, canManage, open }: {
  siteId: string; status: string; q: string; set: (p: Record<string, string>) => void; canManage: boolean; open: (d: DialogState) => void;
}) {
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const params = { site_id: siteId, status: status || undefined, zk_emp_code: q || undefined, page, page_size: size };
  const query = useQuery({ queryKey: ["onsite-identity", "mappings", params], queryFn: () => getMappings(params), placeholderData: keepPreviousData });
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="max-w-xs flex-1"><SearchField label={`Exact ${ID_LABELS.zk}`} value={q} onChange={(v) => { set({ mq: v }); setPage(1); }} /></div>
        <SelectField label="Record status" value={status} onChange={(v) => { set({ status: v }); setPage(1); }}
          options={[{ value: "VERIFIED", label: "Verified" }, { value: "SUPERSEDED", label: "Superseded (corrected)" }, { value: "", label: "All" }]} />
        <Button variant="secondary" onClick={() => downloadIdentityList("mappings", { site_id: siteId })}>Export CSV</Button>
      </div>
      {query.isLoading ? <SkeletonRows /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> : (
        <>
          <DataView<Mapping> caption="Identity mappings" rows={query.data.items} rowKey={(m) => String(m.id)}
            columns={[
              { key: "zk", header: ID_LABELS.zk, cell: (m) => <span className="font-mono">{m.zk_emp_code}</span> },
              { key: "name", header: ID_LABELS.name, cell: (m) => m.employee_name ?? "—" },
              { key: "bhr", header: ID_LABELS.bhr, cell: (m) => <span className="font-mono">{m.bamboohr_id}</span> },
              { key: "num", header: ID_LABELS.number, minWidth: "lg", cell: (m) => <span className="font-mono">{m.employee_number ?? "—"}</span> },
              { key: "status", header: ID_LABELS.mapping, cell: (m) => <MappingStatusBadge m={m} /> },
              { key: "period", header: "Ownership period", cell: (m) => <span className="whitespace-nowrap tabular-nums">{m.valid_from} – {m.valid_to ?? "open"}</span> },
              { key: "by", header: "Verified", minWidth: "xl", cell: (m) => <span className="text-xs">user {m.verified_by_user_id} · {m.verified_at ? new Date(m.verified_at).toLocaleDateString() : "—"} · {m.source}</span> },
              { key: "act", header: "Actions", cell: (m) => <MappingActions m={m} canManage={canManage} open={open} /> },
            ]}
            card={(m) => (
              <div className="space-y-2">
                <div className="flex justify-between gap-2"><span><span className="font-mono">{m.zk_emp_code}</span> → {m.employee_name ?? "—"}</span><MappingStatusBadge m={m} /></div>
                <Facts cols={3} items={[[ID_LABELS.bhr, m.bamboohr_id], [ID_LABELS.number, m.employee_number ?? "—"], ["Period", `${m.valid_from} – ${m.valid_to ?? "open"}`]]} />
                <MappingActions m={m} canManage={canManage} open={open} />
              </div>
            )} />
          <Pager page={page} pageSize={size} total={query.data.total} noun="mapping" busy={query.isFetching} onPage={setPage}
            onPageSize={(n) => { setSize(n); setPage(1); }} />
        </>
      )}
    </div>
  );
}

function MappingStatusBadge({ m }: { m: Mapping }) {
  if (m.status === "SUPERSEDED") return <ToneBadge tone="neutral">Superseded</ToneBadge>;
  if (m.employee_in_directory === false) return <ToneBadge tone="warning">Verified · not in directory</ToneBadge>;
  return <ToneBadge tone="success">{m.valid_to ? "Verified · ended" : "Verified"}</ToneBadge>;
}

function MappingActions({ m, canManage, open }: { m: Mapping; canManage: boolean; open: (d: DialogState) => void }) {
  const live = m.status === "VERIFIED";
  return (
    <span className="flex flex-wrap gap-1">
      <button type="button" className={buttonClass("ghost")} onClick={() => open({ kind: "history", id: m.id })}>History</button>
      {canManage && live && !m.valid_to && <button type="button" className={buttonClass("ghost")} onClick={() => open({ kind: "close", mapping: m })}>End…</button>}
      {canManage && live && <button type="button" className={buttonClass("ghost")} onClick={() => open({ kind: "reassign", mapping: m })}>Reassign…</button>}
      {canManage && live && <button type="button" className={buttonClass("ghost")} onClick={() => open({ kind: "correct", mapping: m })}>Correct…</button>}
    </span>
  );
}

/* ---------------------------------------------------------------- conflicts */

function ConflictsTab({ siteId, canManage, open }: { siteId: string; canManage: boolean; open: (d: DialogState) => void }) {
  const q = useQuery({ queryKey: ["onsite-identity", "conflicts", siteId], queryFn: () => getConflicts({ site_id: siteId }) });
  if (q.isLoading) return <SkeletonRows />;
  if (!q.data) return <ErrorState onRetry={() => q.refetch()} />;
  const c = q.data;
  const period = (m: Mapping) => `${m.employee_name ?? m.bamboohr_id} ${m.valid_from} – ${m.valid_to ?? "open"}`;
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Panel title="Ambiguous reassignment days" subtitle="Days deliberately left unmapped when an ID changed hands">
        {c.ambiguous_reassignment_days.length ? <ul className="space-y-1 text-sm">{c.ambiguous_reassignment_days.map((d) => (
          <li key={`${d.zk_emp_code}-${d.local_date}`}><span className="font-mono">{d.zk_emp_code}</span> · {d.local_date} · {d.events} punch(es) unmapped</li>
        ))}</ul> : <p className="text-sm text-dt-text-secondary">None.</p>}
      </Panel>
      <Panel title="Overlapping mappings" subtitle="Should never occur; attendance on these days is not attributed">
        {c.overlapping_mappings.length ? <ul className="space-y-1 text-sm">{c.overlapping_mappings.map((o, i) => (
          <li key={i}><span className="font-mono">{o.zk_emp_code}</span>: {o.mappings.map(period).join(" / ")}</li>
        ))}</ul> : <p className="text-sm text-dt-text-secondary">None.</p>}
      </Panel>
      <Panel title="Reused ZKBioTime IDs" subtitle="IDs owned by different team members over time">
        {c.reused_codes.length ? <ul className="space-y-1 text-sm">{c.reused_codes.map((r) => (
          <li key={r.zk_emp_code}><span className="font-mono">{r.zk_emp_code}</span>: {r.mappings.map(period).join(" → ")}</li>
        ))}</ul> : <p className="text-sm text-dt-text-secondary">None.</p>}
      </Panel>
      <Panel title="Team members with several IDs" subtitle="Counted once in every headcount">
        {c.employees_with_multiple_codes.length ? <ul className="space-y-1 text-sm">{c.employees_with_multiple_codes.map((e) => (
          <li key={e.bamboohr_id}>{e.mappings[0]?.employee_name ?? e.bamboohr_id} ({ID_LABELS.bhr} {e.bamboohr_id}): {e.codes.join(", ")}</li>
        ))}</ul> : <p className="text-sm text-dt-text-secondary">None.</p>}
      </Panel>
      <Panel title="Active rejections" subtitle="Pairings recorded as NOT the same person">
        {c.active_rejections.length ? <ul className="space-y-1 text-sm">{c.active_rejections.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-2">
            <span><span className="font-mono">{r.zk_emp_code}</span> ≠ {ID_LABELS.bhr} {r.bamboohr_id} ({r.applies_from ?? "all history"} – {r.applies_to ?? "open"}) · {r.reason}</span>
            {canManage && <button type="button" className={buttonClass("ghost")} onClick={() => open({ kind: "withdraw", rejection: r })}>Withdraw…</button>}
          </li>
        ))}</ul> : <p className="text-sm text-dt-text-secondary">None.</p>}
      </Panel>
      <Panel title="Recent changes" subtitle="Audit history of identity changes">
        <ol className="max-h-72 space-y-1 overflow-y-auto text-sm">{c.recent_events.map((e) => (
          <li key={e.id}>{e.at ? new Date(e.at).toLocaleString() : "—"} · <span className="font-medium">{e.action}</span> · {e.entity_type.toLowerCase()} #{e.entity_id} · user {e.actor_user_id}{e.note ? ` — ${e.note}` : ""}</li>
        ))}</ol>
      </Panel>
    </div>
  );
}

/* ------------------------------------------------------------------- import */

function ImportTab() {
  const [file, setFile] = useState<File | null>(null);
  const [dry, setDry] = useState<ImportResult | null>(null);
  const [ack, setAck] = useState(false);
  const [applied, setApplied] = useState<ImportResult | null>(null);
  const check = useMutation({ mutationFn: () => importMappings(file!, { dryRun: true }), onSuccess: (r) => { setDry(r); setApplied(null); setAck(false); } });
  const apply = useMutation({ mutationFn: () => importMappings(file!, { dryRun: false, token: dry?.dry_run_token, acknowledge: ack }), onSuccess: setApplied });
  const rows = dry?.rows ?? [];
  return (
    <div className="space-y-3">
      <InlineAlert tone="info">
        Only HR-approved files in the approved format are accepted (columns: site_id, zk_emp_code, bamboohr_id, valid_from, valid_to,
        evidence, verified_by, verified_on, source_reference). Every row needs its own evidence. A dry run is mandatory; applying is all-or-nothing.
      </InlineAlert>
      <div className="flex flex-wrap items-center gap-2">
        <input type="file" accept=".csv,text/csv" aria-label="Mappings CSV file" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setDry(null); setApplied(null); }} />
        <Button variant="secondary" disabled={!file} loading={check.isPending} onClick={() => check.mutate()}><Upload className="mr-1 size-4" aria-hidden />Dry run</Button>
      </div>
      {check.error && <InlineAlert tone="danger">{errorDetail(check.error).message ?? errorDetail(check.error).error}</InlineAlert>}
      {dry && (
        <Panel title="Dry-run result" subtitle={`${dry.summary.rows} row(s) · ${dry.summary.rows_with_errors} with errors · ${dry.summary.rows_with_warnings} with warnings · nothing saved`}>
          <div className="max-h-80 overflow-y-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-left text-dt-text-secondary"><th>Line</th><th>{ID_LABELS.zk}</th><th>{ID_LABELS.bhr}</th><th>{ID_LABELS.name}</th><th>Period</th><th>Result</th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.line} className="border-t border-dt-border align-top">
                  <td>{r.line}</td><td className="font-mono">{r.zk_emp_code ?? "—"}</td><td className="font-mono">{r.bamboohr_id ?? "—"}</td>
                  <td>{r.employee_name ?? "—"}</td><td>{r.valid_from ?? "—"} – {r.valid_to ?? "open"}</td>
                  <td>{r.errors.length ? <span className="text-dt-danger">{r.errors.join(", ")}</span>
                    : r.warnings.length ? <span className="text-dt-warning">{r.warnings.map((w) => WARNING_LABEL[w.code] ?? w.code).join("; ")}</span>
                    : <span className="text-dt-success">OK</span>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          {dry.can_apply ? (
            <div className="mt-3 space-y-2">
              {dry.requires_warning_acknowledgement && (
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                  I have reviewed every warning above with HR.</label>
              )}
              <Button disabled={dry.requires_warning_acknowledgement && !ack} loading={apply.isPending} onClick={() => apply.mutate()}>
                Apply {dry.summary.rows} verified mapping(s)
              </Button>
            </div>
          ) : <p className="mt-3 text-sm text-dt-danger">Fix every error and run the dry run again. Nothing can be applied while errors remain.</p>}
          {apply.error && <InlineAlert tone="danger">{errorDetail(apply.error).message ?? errorDetail(apply.error).error} — nothing was saved.</InlineAlert>}
          {applied?.applied && <InlineAlert tone="info">Applied batch {applied.batch_id}: {applied.mappings?.length ?? 0} mapping(s) created and audited.</InlineAlert>}
        </Panel>
      )}
    </div>
  );
}

export default function IdentityManagementPage() {
  return (
    <AdminOnly permission={PERM.IDENTITY}>
      <SiteProvider><Suspense fallback={<SkeletonRows />}><IdentityManagement /></Suspense></SiteProvider>
    </AdminOnly>
  );
}
