"use client";

import { useQuery } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { CircleAlert, CircleCheck, Fingerprint, GitMerge, Percent, ShieldCheck, Timer } from "lucide-react";
import { StackedBarChart } from "@/components/charts";
import { PeriodControl } from "@/components/FilterBar";
import { buttonClass, cx, EmptyPanel, focusRing, InlineAlert, KpiCard, Panel, SkeletonRows } from "@/components/kit";
import { FEED_LABEL, ID_LABELS } from "@/lib/format";
import { getCoverage, type Coverage } from "@/lib/identity";
import { fmtNum, fmtPeriod, fmtShortDay, fmtDay, type Period } from "@/lib/period";
import type { FeedState } from "@/lib/types";

const HELP = {
  observed: "Distinct ZKBioTime IDs (biometric codes) with at least one punch in the period. An ID is not a team member: one person can hold several IDs, and an ID can change hands.",
  verified: "ZKBioTime IDs with at least one punch in the period attributed through an administrator-verified mapping. 'Partly' means some of the ID's days fall outside its verified period.",
  unmapped: "ZKBioTime IDs whose punches in the period are not covered by any verified mapping. Their attendance is stored safely and appears in team member records once verified.",
  punches: "Punches in the period not attributed to a verified team member. Counted in punches (not IDs or people).",
  coverage: "Share of the period's punches attributed through verified mappings (verified punches ÷ all punches).",
  conflicts: "Days that cannot be attributed safely: overlapping mappings, conflicting coverage, or reassignment days deliberately left unmapped.",
};

function Ingestion({ c }: { c: Coverage }) {
  const state = (c.ingestion.feed_state ?? "NOT_SYNCED") as FeedState;
  const healthy = state === "FRESH";
  const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—");
  return (
    <InlineAlert tone={healthy ? "info" : "warning"}>
      <span className="font-medium">Attendance ingestion: {FEED_LABEL[state] ?? state}.</span>{" "}
      Latest event received {when(c.ingestion.latest_received_utc)} · last successful sync {when(c.ingestion.last_successful_sync_at)}.{" "}
      {healthy
        ? <>Punches from unmapped ZKBioTime IDs are stored safely; the remaining step is identity verification and mapping by the administration team.</>
        : <>This is a feed/synchronisation matter, separate from the mapping backlog — see Site Health. Stored punches are not affected.</>}
    </InlineAlert>
  );
}

function CoverageBar({ c }: { c: Coverage }) {
  const { verified, unmapped, total } = c.punches;
  const vp = total ? (verified / total) * 100 : 0;
  return (
    <div className="space-y-2">
      <div className="flex h-4 w-full overflow-hidden rounded-full bg-dt-border/60" role="img"
        aria-label={`${fmtNum(verified)} of ${fmtNum(total)} punches verified (${c.punches.coverage_pct ?? 0}%), ${fmtNum(unmapped)} unmapped`}>
        <span className="h-full bg-dt-success" style={{ width: `${vp}%` }} />
        <span className="h-full bg-dt-amber" style={{ width: `${100 - vp}%` }} />
      </div>
      <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <div><dt className="flex items-center gap-1 text-xs text-dt-text-secondary"><span className="size-2.5 rounded-sm bg-dt-success" />Verified punches</dt>
          <dd className="font-semibold tabular-nums">{fmtNum(verified)}</dd></div>
        <div><dt className="flex items-center gap-1 text-xs text-dt-text-secondary"><span className="size-2.5 rounded-sm bg-dt-amber" />Unmapped punches</dt>
          <dd className="font-semibold tabular-nums">{fmtNum(unmapped)}</dd></div>
        <div><dt className="text-xs text-dt-text-secondary">IDs: fully · partly verified</dt>
          <dd className="font-semibold tabular-nums">{fmtNum(c.ids.fully_verified)} · {fmtNum(c.ids.partly_verified)}</dd></div>
        <div><dt className="text-xs text-dt-text-secondary">Verified team members</dt>
          <dd className="font-semibold tabular-nums">{fmtNum(c.verified_team_members)}</dd></div>
      </dl>
    </div>
  );
}

function TopUnmapped({ c, onMap, onInvestigate, canManage }: {
  c: Coverage; onMap: (code: string) => void; onInvestigate: (code: string) => void; canManage: boolean;
}) {
  if (!c.top_unmapped.length) {
    return <EmptyPanel icon={CircleCheck} title="No unmapped activity" description="Every punch in this period is attributed to a verified team member." />;
  }
  const max = Math.max(...c.top_unmapped.map((x) => x.unmapped_punches));
  return (
    <ol className="space-y-1.5" aria-label="ZKBioTime IDs with the most unmapped punches">
      {c.top_unmapped.map((x, i) => (
        <li key={x.zk_emp_code} className="grid grid-cols-[2rem_6rem_1fr_auto] items-center gap-2 text-sm">
          <span className="text-xs tabular-nums text-dt-text-secondary">{i + 1}.</span>
          <button type="button" onClick={() => onInvestigate(x.zk_emp_code)} title="Investigate this ZKBioTime ID"
            className={cx("truncate rounded text-left font-mono font-medium text-dt-burnt-orange hover:underline", focusRing)}>{x.zk_emp_code}</button>
          <span className="relative h-5 overflow-hidden rounded bg-dt-surface-warm" title={`${fmtNum(x.unmapped_punches)} unmapped punches on ${x.unmapped_days} day(s), ${x.first_unmapped} – ${x.last_unmapped}`}>
            <span className="absolute inset-y-0 left-0 rounded bg-dt-amber/80" style={{ width: `${(x.unmapped_punches / max) * 100}%` }} />
            <span className="relative px-2 text-xs leading-5 tabular-nums">
              {fmtNum(x.unmapped_punches)} punches · {x.unmapped_days} day(s){x.mapped_now ? " · partly verified" : ""}
            </span>
          </span>
          {canManage
            ? <button type="button" className={buttonClass("secondary")} onClick={() => onMap(x.zk_emp_code)}>Map…</button>
            : <span />}
        </li>
      ))}
    </ol>
  );
}

/** Identity Management overview: real mirror + mapping figures for the
 *  selected site and period. IDs, punches and team members are kept apart. */
export function CoverageDashboard({ siteId, siteName, today, period, onPeriod, canManage, onMap, onInvestigate }: {
  siteId: string; siteName: string; today: string; period: Period; onPeriod: (p: Period) => void; canManage: boolean;
  onMap: (code: string) => void; onInvestigate: (code: string) => void;
}) {
  const q = useQuery({
    queryKey: ["onsite-identity", "coverage", siteId, period.from, period.to],
    queryFn: () => getCoverage({ site_id: siteId, date_from: period.from, date_to: period.to }),
    refetchInterval: 60_000,
  });
  const label = fmtPeriod(period, today);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PeriodControl value={period} today={today} onChange={onPeriod} />
        <span className="text-xs text-dt-text-secondary">{label} · {siteName} · site-local dates</span>
      </div>
      {q.isLoading ? <SkeletonRows label="Loading identity coverage…" /> : !q.data ? <ErrorState onRetry={() => q.refetch()} /> : (() => {
        const c = q.data;
        const conflicts = c.unresolved_conflicts.total;
        return (
          <>
            <Ingestion c={c} />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 2xl:grid-cols-6">
              <KpiCard label={`${ID_LABELS.zk}s observed`} value={fmtNum(c.ids.observed)} icon={Fingerprint} help={HELP.observed}
                sub={<span>Biometric IDs, not people</span>} />
              <KpiCard label="Verified IDs" value={fmtNum(c.ids.verified)} icon={ShieldCheck} tone="success" help={HELP.verified}
                sub={<span>{fmtNum(c.ids.fully_verified)} fully · {fmtNum(c.ids.partly_verified)} partly</span>} />
              <KpiCard label="Unmapped IDs" value={fmtNum(c.ids.unmapped)} icon={Timer} tone={c.ids.unmapped ? "attention" : "default"}
                help={HELP.unmapped} sub={<span>Awaiting verification</span>} />
              <KpiCard label="Unmapped punches" value={fmtNum(c.punches.unmapped)} icon={GitMerge} help={HELP.punches}
                sub={<span>of {fmtNum(c.punches.total)} punches, stored safely</span>} />
              <KpiCard label="Verified coverage" value={c.punches.coverage_pct === null ? "—" : `${c.punches.coverage_pct}%`} icon={Percent}
                tone="brand" help={HELP.coverage} sub={<span>of punches in the period</span>} />
              <KpiCard label="Unresolved conflicts" value={fmtNum(conflicts)} icon={CircleAlert} tone={conflicts ? "danger" : "default"}
                help={HELP.conflicts} sub={<span>{conflicts ? "Review under Conflicts & history" : "None"}</span>} />
            </div>
            {c.punches.total === 0 ? (
              <EmptyPanel icon={Fingerprint} title="No attendance recorded in this period"
                description="Choose a wider period. No punches were mirrored for this site and period." />
            ) : (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
                <Panel title="Verified vs unmapped punches" subtitle={`Punches per site-local day · ${label}`} className="xl:col-span-3">
                  <StackedBarChart primaryLabel="Verified" secondaryLabel="Unmapped" measure="punches"
                    summary={`Verified and unmapped punches per day, ${label}, ${siteName}`}
                    tickEvery={c.trend.length > 31 ? [21, 14] : c.trend.length > 7 ? [7, 5] : [1, 1]}
                    data={c.trend.map((t) => ({ key: t.date, label: fmtDay(t.date, true), tick: fmtShortDay(t.date),
                      primary: t.verified_punches, secondary: t.unmapped_punches }))} />
                </Panel>
                <Panel title="Mapping coverage" subtitle="Share of punches attributed to verified team members" className="xl:col-span-2">
                  <CoverageBar c={c} />
                </Panel>
                <Panel title="Highest-priority unmapped IDs" subtitle="Ranked by unmapped punches in the period · select an ID to investigate or map it"
                  className="xl:col-span-5">
                  <TopUnmapped c={c} canManage={canManage} onMap={onMap} onInvestigate={onInvestigate} />
                </Panel>
              </div>
            )}
          </>
        );
      })()}
    </div>
  );
}
