"use client";

import { Suspense, useState } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Button, ErrorState, MetricCard } from "@dijione/design-system";
import { CircleAlert, CircleCheck, Fingerprint, Search, Upload, Users } from "lucide-react";
import { AdminOnly } from "@/components/AdminOnly";
import { DataView, Facts } from "@/components/DataView";
import { HBarList, SegmentBar } from "@/components/charts";
import { PeriodControl, SearchField, SelectField, SiteSelect } from "@/components/FilterBar";
import { buttonClass, cx, EmptyPanel, focusRing, InfoTip, InlineAlert, PageTop, Pager, Panel, RowActions, SkeletonRows } from "@/components/kit";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { ToneBadge } from "@/components/ToneBadge";
import {
  CloseDialog, CodeDialog, CorrectDialog, HistoryDialog, MapDialog, ReassignDialog, RejectDialog, WithdrawDialog,
} from "@/components/identity/dialogs";
import { ID_LABELS } from "@/lib/format";
import {
  dispositionState, downloadIdentityList, errorDetail, getConflicts, getCoverage, getMappings, getReadiness, getUnmapped,
  getUnmappedSummary, importMappings, REVIEW_STATE, reviewStateOf, WARNING_LABEL, type ImportResult, type Mapping,
  type Rejection, type ReviewState, type UnmappedRow,
} from "@/lib/identity";
import { hasPermission, PERM, useOnsiteScope } from "@/lib/onsite-scope";
import { fmtDay, fmtNum, fmtPeriod, fmtShortDay, normalizePeriod, presetPeriod, type Period } from "@/lib/period";
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
  const [s, set] = useUrlState({ tab: "overview", q: "", status: "VERIFIED", mq: "", from: "", to: "", sort: "", code: "" });
  const tab = (TABS.some(([t]) => t === s.tab) ? s.tab : "overview") as Tab;
  const period = s.from && s.to ? normalizePeriod({ from: s.from, to: s.to }) : presetPeriod("30d", site.today);
  const [dialog, setDialog] = useState<DialogState>(null);
  const close = () => setDialog(null);
  // The investigation view is URL state, so an ID can be deep-linked and the
  // browser Back button closes it; every other dialog is local.
  const open: Open = (d) => (d?.kind === "code" ? set({ code: d.code }) : setDialog(d));

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
            onInvestigate={(code) => set({ code })} />
        )}
        {tab === "readiness" && <ReadinessTab siteId={site.site_id} canManage={canManage} open={open} />}
        {tab === "unmapped" && <UnmappedTab siteId={site.site_id} q={s.q} setQ={(q) => set({ q })} sort={s.sort} setSort={(v) => set({ sort: v })}
          canManage={canManage} open={open}
          backlog={<BacklogPanel siteId={site.site_id} period={period} today={site.today} onPeriod={(p) => set({ from: p.from, to: p.to })} />} />}
        {tab === "mappings" && <MappingsTab siteId={site.site_id} status={s.status} q={s.mq} set={set} canManage={canManage} open={open} />}
        {tab === "conflicts" && <ConflictsTab siteId={site.site_id} timeZone={site.time_zone} canManage={canManage} open={open} />}
        {tab === "import" && (canManage ? <ImportTab /> : <InlineAlert tone="info">Importing requires the Manage Identity Mappings permission.</InlineAlert>)}
      </div>

      {dialog?.kind === "map" && <MapDialog siteId={site.site_id} code={dialog.code} onClose={close} />}
      {dialog?.kind === "reject" && <RejectDialog siteId={site.site_id} code={dialog.code} onClose={close} />}
      {s.code && !dialog && (
        <CodeDialog siteId={site.site_id} code={s.code} onClose={() => set({ code: "" })} canManage={canManage}
          onMap={(code) => { set({ code: "" }); setDialog({ kind: "map", code }); }}
          onReject={(code) => { set({ code: "" }); setDialog({ kind: "reject", code }); }} />
      )}
      {dialog?.kind === "close" && <CloseDialog mapping={dialog.mapping} onClose={close} />}
      {dialog?.kind === "correct" && <CorrectDialog mapping={dialog.mapping} onClose={close} />}
      {dialog?.kind === "reassign" && <ReassignDialog mapping={dialog.mapping} onClose={close} />}
      {dialog?.kind === "history" && <HistoryDialog mappingId={dialog.id} onClose={close} />}
      {dialog?.kind === "withdraw" && <WithdrawDialog rejection={dialog.rejection} onClose={close} />}
    </div>
  );
}

/* ---------------------------------------------------------------- readiness */

type Open = (d: DialogState) => void;

function ReviewBadge({ state }: { state: ReviewState }) {
  const r = REVIEW_STATE[state];
  return (
    <span className="inline-flex items-center gap-0.5">
      <ToneBadge tone={r.tone}>{r.label}</ToneBadge>
      <InfoTip text={r.help} label={`What "${r.label}" means`} />
    </span>
  );
}

/** Accessible primary link into the investigation view of one ID. */
function IdLink({ code, open }: { code: string; open: Open }) {
  return (
    <button type="button" onClick={() => open({ kind: "code", code })} aria-label={`Investigate ZKBioTime ID ${code}`}
      className={cx("rounded font-mono font-medium text-dt-burnt-orange underline-offset-2 hover:underline", focusRing)}>
      {code}
    </button>
  );
}

function ReadinessTab({ siteId, canManage, open }: { siteId: string; canManage: boolean; open: Open }) {
  const q = useQuery({ queryKey: ["onsite-identity", "readiness", siteId], queryFn: () => getReadiness({ site_id: siteId, days: 30 }) });
  if (q.isLoading) return <SkeletonRows label="Loading readiness…" />;
  if (!q.data) return <ErrorState onRetry={() => q.refetch()} />;
  const r = q.data;
  const c = r.unresolved_conflicts;
  const top = r.high_volume_outstanding_codes;
  const max = Math.max(1, ...top.map((x) => x.unmapped_events));
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
        Last {r.window_days} site days ({fmtDay(r.date_from, true)} – {fmtDay(r.date_to, true)}): {fmtNum(r.identified_punches)} of {fmtNum(r.total_punches)} punches attributed ·{" "}
        {fmtNum(r.active_codes)} active IDs · {fmtNum(r.unmapped_punches)} unmapped punches · {fmtNum(r.verified_mappings)} verified mappings ·{" "}
        {r.mappings_without_evidence} without evidence · directory {r.directory_available ? "available" : "unavailable"}.
      </p>
      <InlineAlert tone="info">These figures inform the production decision; the threshold is approved separately by the owner with HR/IT. Nothing here is automatic.</InlineAlert>
      <Panel title="High-volume outstanding IDs" subtitle="Top unmapped ZKBioTime IDs by unmapped punches in the window, with their review status. Select an ID to investigate it.">
        {top.length === 0 ? <p className="text-sm text-dt-text-secondary">No unmapped activity in the window.</p> : (
          <ol className="space-y-2" aria-label="High-volume outstanding ZKBioTime IDs">
            {top.map((x, i) => (
              <li key={x.zk_emp_code} className="grid grid-cols-[1.75rem_minmax(0,5.5rem)_minmax(0,1fr)] items-center gap-x-2 gap-y-1 text-sm sm:grid-cols-[1.75rem_minmax(0,5.5rem)_minmax(0,1fr)_auto_auto]">
                <span className="text-xs tabular-nums text-dt-text-secondary">{i + 1}.</span>
                <span className="min-w-0 truncate"><IdLink code={x.zk_emp_code} open={open} /></span>
                <span className="relative h-5 overflow-hidden rounded bg-dt-surface-warm" title={`${fmtNum(x.unmapped_events)} unmapped punches`}>
                  <span className="absolute inset-y-0 left-0 rounded bg-dt-amber/80" style={{ width: `${(x.unmapped_events / max) * 100}%` }} />
                  <span className="relative px-2 text-xs leading-5 tabular-nums">{fmtNum(x.unmapped_events)} punches</span>
                </span>
                <span className="col-span-3 col-start-2 sm:col-span-1 sm:col-start-auto"><ReviewBadge state={dispositionState(x.disposition)} /></span>
                <span className="col-span-3 col-start-2 sm:col-span-1 sm:col-start-auto">
                  <RowActions label={`ZKBioTime ID ${x.zk_emp_code}`}
                    primary={canManage ? { label: "Map…", ariaLabel: `Map ZKBioTime ID ${x.zk_emp_code}`, onSelect: () => open({ kind: "map", code: x.zk_emp_code }) }
                      : { label: "Investigate", onSelect: () => open({ kind: "code", code: x.zk_emp_code }) }} />
                </span>
              </li>
            ))}
          </ol>
        )}
      </Panel>
    </div>
  );
}

/* ----------------------------------------------------------------- unmapped */

function BacklogPanel({ siteId, period, today, onPeriod }: { siteId: string; period: Period; today: string; onPeriod: (p: Period) => void }) {
  const sum = useQuery({ queryKey: ["onsite-identity", "unmapped-summary", siteId], queryFn: () => getUnmappedSummary({ site_id: siteId }) });
  const cov = useQuery({ queryKey: ["onsite-identity", "coverage", siteId, period.from, period.to],
    queryFn: () => getCoverage({ site_id: siteId, date_from: period.from, date_to: period.to }) });
  const label = fmtPeriod(period, today);
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <Panel title="Biometric ID distribution" subtitle={`ZKBioTime IDs with punches · ${label} · IDs are not team members`}
        action={<PeriodControl value={period} today={today} onChange={onPeriod} />} className="xl:col-span-3">
        {cov.isLoading ? <SkeletonRows rows={2} /> : !cov.data ? <ErrorState onRetry={() => cov.refetch()} /> : (
          <SegmentBar unit="IDs" summary={`ZKBioTime IDs by verification, ${label}`} empty="No punches recorded for this site and period."
            segments={[
              { key: "full", label: "Fully verified", value: cov.data.ids.fully_verified, tone: "success", help: "Every punch day in the period is covered by a verified mapping." },
              { key: "part", label: "Partly verified", value: cov.data.ids.partly_verified, tone: "warning", help: REVIEW_STATE.PARTLY_VERIFIED.help },
              { key: "none", label: "Entirely unmapped", value: cov.data.ids.observed - cov.data.ids.verified, tone: "danger", help: "No punch day in the period is covered by a verified mapping." },
            ]} />
        )}
      </Panel>
      {sum.isLoading ? <div className="xl:col-span-3"><SkeletonRows rows={3} /></div> : !sum.data ? <div className="xl:col-span-3"><ErrorState onRetry={() => sum.refetch()} /></div> : (
        <>
          <Panel title="Review status" subtitle={`${fmtNum(sum.data.outstanding_ids)} outstanding IDs · all mirrored history`}>
            <SegmentBar unit="IDs" summary="Outstanding ZKBioTime IDs by review status" empty="No outstanding IDs."
              segments={(Object.keys(REVIEW_STATE) as ReviewState[]).map((k) => ({
                key: k, label: REVIEW_STATE[k].label, value: sum.data!.review[k], help: REVIEW_STATE[k].help,
                tone: k === "REJECTED_ASSOCIATION" ? "neutral" : k === "PARTLY_VERIFIED" ? "warning" : "danger",
              }))} />
          </Panel>
          <Panel title="Backlog age" subtitle={`Since the oldest unmapped punch day · as of ${fmtDay(sum.data.as_of, true)}`}>
            <HBarList unit="IDs" summary="Outstanding IDs by age of their oldest unmapped punch day"
              items={sum.data.aging.map((b) => ({ key: b.label, label: b.label, value: b.ids, sub: `${fmtNum(b.unmapped_punches)} unmapped punches` }))} />
          </Panel>
          <Panel title="Recent activity" subtitle="Latest unmapped punch day of each outstanding ID">
            <HBarList unit="IDs" tone="brand" summary="Outstanding IDs by recency of their latest unmapped punch"
              items={sum.data.recency.map((b) => ({ key: b.label, label: b.label, value: b.ids, sub: `${fmtNum(b.unmapped_punches)} unmapped punches` }))} />
          </Panel>
        </>
      )}
    </div>
  );
}

const UNMAPPED_SORT = new Set(["unmapped_events", "unmapped_days", "last_unmapped", "first_seen", "zk_emp_code", "event_count"]);

function UnmappedTab({ siteId, q, setQ, sort, setSort, canManage, open, backlog }: {
  siteId: string; q: string; setQ: (v: string) => void; sort: string; setSort: (v: string) => void; canManage: boolean; open: Open;
  backlog: React.ReactNode;
}) {
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [exportState, setExportState] = useState<"idle" | "busy" | "error">("idle");
  const sortKey = UNMAPPED_SORT.has(sort.replace(/^-/, "")) ? sort : "-unmapped_events";
  const params = { site_id: siteId, q: q || undefined, sort: sortKey, page, page_size: size };
  const query = useQuery({ queryKey: ["onsite-identity", "unmapped", params], queryFn: () => getUnmapped(params), placeholderData: keepPreviousData });
  const total = query.data?.total ?? 0;
  return (
    <div className="space-y-4">
      {backlog}
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-end gap-2">
          <div className="min-w-0 max-w-sm flex-1"><SearchField label={`Search ${ID_LABELS.zk}`} value={q} onChange={(v) => { setQ(v); setPage(1); }} /></div>
          {q && <button type="button" className={buttonClass("ghost")} onClick={() => { setQ(""); setPage(1); }}>Clear search</button>}
        </div>
        <Button variant="secondary" loading={exportState === "busy"} onClick={async () => {
          setExportState("busy");
          try { await downloadIdentityList("unmapped", { site_id: siteId }); setExportState("idle"); } catch { setExportState("error"); }
        }}>Export CSV</Button>
      </div>
      {exportState === "error" && <p className="text-sm text-dt-danger" role="alert">Export failed. Please try again.</p>}
      <p className="text-sm text-dt-text-secondary">IDs with attendance that is not covered by a verified mapping on at least one day. Their punches are stored and excluded from attendance views and exports until verified.</p>
      {query.isLoading ? <SkeletonRows /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> : total === 0 ? (
        <EmptyPanel icon={q ? Search : CircleCheck} title={q ? "No matching ZKBioTime IDs" : "No outstanding IDs"}
          description={q ? `No outstanding ID contains "${q}".` : "Every punch day at this site is covered by a verified mapping."} />
      ) : (
        <>
          <DataView<UnmappedRow> caption="Unmapped ZKBioTime IDs" rows={query.data.items} rowKey={(r) => `${r.site_id}:${r.zk_emp_code}`}
            sort={sortKey} onSort={(v) => { setSort(v); setPage(1); }} rowLabel={(r) => `ZKBioTime ID ${r.zk_emp_code}`}
            columns={[
              { key: "id", header: ID_LABELS.zk, sort: "zk_emp_code", cell: (r) => <IdLink code={r.zk_emp_code} open={open} /> },
              { key: "events", header: "Punches", help: "Unmapped punches of all punches recorded for this ID.", sort: "unmapped_events", align: "right", cell: (r) => <span className="tabular-nums">{fmtNum(r.unmapped_events)} <span className="block text-xs text-dt-text-secondary">of {fmtNum(r.event_count)}</span></span> },
              { key: "days", header: "Days", help: "Days with at least one unmapped punch.", sort: "unmapped_days", align: "right", cell: (r) => fmtNum(r.unmapped_days) },
              { key: "range", header: "Period", help: "First to latest day with an unmapped punch. Sorts by the latest day.", sort: "last_unmapped", cell: (r) => <span className="tabular-nums">{fmtShortDay(r.first_unmapped)} – {fmtShortDay(r.last_unmapped)}</span> },
              { key: "status", header: "Review", cell: (r) => <ReviewBadge state={reviewStateOf(r)} /> },
              { key: "seen", header: "All attendance", sort: "first_seen", minWidth: "xl", cell: (r) => <span className="tabular-nums">{fmtShortDay(r.first_seen)} – {fmtShortDay(r.last_seen)} · {fmtNum(r.activity_days)} days</span> },
              { key: "hint", header: "Unverified hint", minWidth: "xl", cell: (r) => <Hints r={r} /> },
              { key: "act", header: <span className="sr-only">Actions</span>, align: "right", cell: (r) => <UnmappedActions r={r} canManage={canManage} open={open} /> },
            ]}
            card={(r) => (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2"><IdLink code={r.zk_emp_code} open={open} /><ReviewBadge state={reviewStateOf(r)} /></div>
                <Facts cols={3} items={[["Unmapped punches", `${fmtNum(r.unmapped_events)} of ${fmtNum(r.event_count)}`], ["Unmapped days", fmtNum(r.unmapped_days)],
                  ["Unmapped period", `${fmtShortDay(r.first_unmapped)} – ${fmtShortDay(r.last_unmapped)}`], ["All attendance", `${fmtShortDay(r.first_seen)} – ${fmtShortDay(r.last_seen)}`]]} />
                <Hints r={r} />
                <UnmappedActions r={r} canManage={canManage} open={open} />
              </div>
            )} />
          <Pager page={page} pageSize={size} total={total} noun="ID" busy={query.isFetching} onPage={setPage}
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

function UnmappedActions({ r, canManage, open }: { r: UnmappedRow; canManage: boolean; open: Open }) {
  const code = r.zk_emp_code;
  const investigate = { label: "Investigate", ariaLabel: `Investigate ZKBioTime ID ${code}`, onSelect: () => open({ kind: "code", code }) };
  if (!canManage) return <RowActions label={`ZKBioTime ID ${code}`} primary={investigate} />;
  return (
    <RowActions label={`ZKBioTime ID ${code}`}
      primary={{ label: "Map…", ariaLabel: `Map ZKBioTime ID ${code}`, onSelect: () => open({ kind: "map", code }) }}
      more={[investigate, { label: "Not this person…", onSelect: () => open({ kind: "reject", code }) }]} />
  );
}

/* ----------------------------------------------------------------- mappings */

function MappingsTab({ siteId, status, q, set, canManage, open }: {
  siteId: string; status: string; q: string; set: (p: Record<string, string>) => void; canManage: boolean; open: Open;
}) {
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [exportError, setExportError] = useState(false);
  const params = { site_id: siteId, status: status || undefined, zk_emp_code: q || undefined, page, page_size: size };
  const query = useQuery({ queryKey: ["onsite-identity", "mappings", params], queryFn: () => getMappings(params), placeholderData: keepPreviousData });
  const filtered = Boolean(q) || status !== "VERIFIED";
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-0 max-w-xs flex-1"><SearchField label={`Exact ${ID_LABELS.zk}`} value={q} onChange={(v) => { set({ mq: v }); setPage(1); }} /></div>
        <SelectField label="Record status" value={status} onChange={(v) => { set({ status: v }); setPage(1); }}
          options={[{ value: "VERIFIED", label: "Verified" }, { value: "SUPERSEDED", label: "Superseded (corrected)" }, { value: "", label: "All" }]} />
        {filtered && <button type="button" className={buttonClass("ghost")} onClick={() => { set({ mq: "", status: "VERIFIED" }); setPage(1); }}>Reset filters</button>}
        <Button variant="secondary" onClick={async () => { setExportError(false); try { await downloadIdentityList("mappings", { site_id: siteId }); } catch { setExportError(true); } }}>Export CSV</Button>
      </div>
      {exportError && <p className="text-sm text-dt-danger" role="alert">Export failed. Please try again.</p>}
      {query.isLoading ? <SkeletonRows /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> : query.data.total === 0 ? (
        <EmptyPanel icon={filtered ? Search : Fingerprint} title={filtered ? "No mappings match these filters" : "No verified mappings yet"}
          description={filtered ? "Change the ID or record status, or reset the filters." : "Verified mappings appear here once an administrator maps a ZKBioTime ID."} />
      ) : (
        <>
          <DataView<Mapping> caption="Identity mappings" rows={query.data.items} rowKey={(m) => String(m.id)} rowLabel={(m) => `mapping ${m.zk_emp_code}`}
            columns={[
              { key: "zk", header: ID_LABELS.zk, cell: (m) => <IdLink code={m.zk_emp_code} open={open} /> },
              { key: "name", header: "Team Member", cell: (m) => (
                <span className="block min-w-0"><span className="block font-medium text-dt-text-primary">{m.employee_name ?? "—"}</span>
                  <span className="block text-xs text-dt-text-secondary">{ID_LABELS.bhr} <span className="font-mono">{m.bamboohr_id}</span></span></span>
              ) },
              { key: "num", header: ID_LABELS.number, minWidth: "xl", cell: (m) => <span className="font-mono">{m.employee_number ?? "—"}</span> },
              { key: "status", header: ID_LABELS.mapping, cell: (m) => <MappingStatusBadge m={m} /> },
              { key: "period", header: "Ownership period", cell: (m) => <span className="tabular-nums">{fmtShortDay(m.valid_from)} – {m.valid_to ? fmtShortDay(m.valid_to) : "open"}</span> },
              { key: "by", header: "Verified", minWidth: "xl", cell: (m) => <span className="text-xs">user {m.verified_by_user_id} · {m.verified_at ? new Date(m.verified_at).toLocaleDateString() : "—"} · {m.source}</span> },
              { key: "act", header: <span className="sr-only">Actions</span>, align: "right", cell: (m) => <MappingActions m={m} canManage={canManage} open={open} /> },
            ]}
            card={(m) => (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2"><span className="min-w-0"><IdLink code={m.zk_emp_code} open={open} /> → {m.employee_name ?? "—"}</span><MappingStatusBadge m={m} /></div>
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

function MappingActions({ m, canManage, open }: { m: Mapping; canManage: boolean; open: Open }) {
  const live = m.status === "VERIFIED";
  const history = { label: "History", ariaLabel: `History of mapping ${m.zk_emp_code}`, onSelect: () => open({ kind: "history", id: m.id }) };
  const more = canManage && live ? [
    ...(!m.valid_to ? [{ label: "End ownership…", onSelect: () => open({ kind: "close", mapping: m }) }] : []),
    { label: "Reassign ID…", onSelect: () => open({ kind: "reassign", mapping: m }) },
    { label: "Correct…", onSelect: () => open({ kind: "correct", mapping: m }) },
  ] : [];
  return <RowActions label={`mapping ${m.zk_emp_code}`} primary={history} more={more} />;
}

/* ---------------------------------------------------------------- conflicts */

function ConflictsTab({ siteId, timeZone, canManage, open }: { siteId: string; timeZone: string | null; canManage: boolean; open: Open }) {
  const q = useQuery({ queryKey: ["onsite-identity", "conflicts", siteId], queryFn: () => getConflicts({ site_id: siteId }) });
  if (q.isLoading) return <SkeletonRows />;
  if (!q.data) return <ErrorState onRetry={() => q.refetch()} />;
  const c = q.data;
  const period = (m: Mapping) => `${m.employee_name ?? m.bamboohr_id} ${m.valid_from} – ${m.valid_to ?? "open"}`;
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Panel title="Ambiguous reassignment days" subtitle="Days deliberately left unmapped when an ID changed hands">
        {c.ambiguous_reassignment_days.length ? <ul className="space-y-1 text-sm">{c.ambiguous_reassignment_days.map((d) => (
          <li key={`${d.zk_emp_code}-${d.local_date}`}><IdLink code={d.zk_emp_code} open={open} /> · {d.local_date} · {d.events} punch(es) unmapped</li>
        ))}</ul> : <p className="text-sm text-dt-text-secondary">None.</p>}
      </Panel>
      <Panel title="Overlapping mappings" subtitle="Should never occur; attendance on these days is not attributed">
        {c.overlapping_mappings.length ? <ul className="space-y-1 text-sm">{c.overlapping_mappings.map((o, i) => (
          <li key={i}><IdLink code={o.zk_emp_code} open={open} />: {o.mappings.map(period).join(" / ")}</li>
        ))}</ul> : <p className="text-sm text-dt-text-secondary">None.</p>}
      </Panel>
      <Panel title="Reused ZKBioTime IDs" subtitle="IDs owned by different team members over time">
        {c.reused_codes.length ? <ul className="space-y-1 text-sm">{c.reused_codes.map((r) => (
          <li key={r.zk_emp_code}><IdLink code={r.zk_emp_code} open={open} />: {r.mappings.map(period).join(" → ")}</li>
        ))}</ul> : <p className="text-sm text-dt-text-secondary">None.</p>}
      </Panel>
      <Panel title="Team members with several IDs" subtitle="Counted once in every headcount">
        {c.employees_with_multiple_codes.length ? <ul className="space-y-1 text-sm">{c.employees_with_multiple_codes.map((e) => (
          <li key={e.bamboohr_id}>{e.mappings[0]?.employee_name ?? e.bamboohr_id} ({ID_LABELS.bhr} {e.bamboohr_id}): {e.codes.map((code, i) => <span key={code}>{i > 0 && ", "}<IdLink code={code} open={open} /></span>)}</li>
        ))}</ul> : <p className="text-sm text-dt-text-secondary">None.</p>}
      </Panel>
      <Panel title="Active rejections" subtitle="Pairings recorded as NOT the same person">
        {c.active_rejections.length ? <ul className="space-y-1 text-sm">{c.active_rejections.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-2">
            <span><IdLink code={r.zk_emp_code} open={open} /> ≠ {ID_LABELS.bhr} {r.bamboohr_id} ({r.applies_from ?? "all history"} – {r.applies_to ?? "open"}) · {r.reason}</span>
            {canManage && <button type="button" className={buttonClass("ghost")} onClick={() => open({ kind: "withdraw", rejection: r })}>Withdraw…</button>}
          </li>
        ))}</ul> : <p className="text-sm text-dt-text-secondary">None.</p>}
      </Panel>
      <Panel title="Recent changes" subtitle="Audit history of identity changes">
        <ol className="max-h-72 space-y-1 overflow-y-auto text-sm">{c.recent_events.map((e) => (
          <li key={e.id}>{e.at ? new Date(e.at).toLocaleString([], { dateStyle: "medium", timeStyle: "short", ...(timeZone ? { timeZone } : {}) }) : "—"} · <span className="font-medium">{e.action}</span> · {e.entity_type.toLowerCase()} #{e.entity_id} · user {e.actor_user_id}{e.note ? ` — ${e.note}` : ""}</li>
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
