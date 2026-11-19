"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { CalendarSearch } from "lucide-react";
import { AttendanceReviewDialog, type ReviewTarget } from "@/components/AttendanceReviewDialog";
import { DataView } from "@/components/DataView";
import { MappingStateBadge } from "@/components/FlagChips";
import { ToneBadge } from "@/components/ToneBadge";
import { buttonClass, cx, EmptyPanel, focusRing, Pager, SkeletonRows } from "@/components/kit";
import { getActivity, getDailyActivity, type DailyRow, type DailySummary, type MappingFilter } from "@/lib/dashboard";
import { localTime } from "@/lib/flags";
import { formatRecordedSpan, MAPPING_STATE, RECORDED_SPAN_HELP, SEQUENCE_LABEL } from "@/lib/format";
import { liveQuery } from "@/lib/live-refresh";
import { fmtDay, fmtNum } from "@/lib/period";
import { STATUS_LABEL, STATUS_TONE } from "@/lib/reviews";

export type DailyFilters = {
  site_id: string; date_from: string; date_to: string; mapping: MappingFilter; q?: string; emp_code?: string;
  terminal?: string; review_status?: string;
};

function identityLabel(r: DailyRow): string {
  return r.mapping_state === "VERIFIED" ? r.employee_name ?? `BHR ID ${r.bamboohr_id}` : `ZKBioTime ID ${r.emp_code}`;
}

function Identity({ r }: { r: DailyRow }) {
  if (r.mapping_state !== "VERIFIED") {
    return (
      <span className="min-w-0">
        <span className="block font-mono font-medium text-dt-text-primary">ZKBioTime ID {r.emp_code}</span>
        <span className="block text-xs text-dt-text-secondary">{r.mapping_state === "CONFLICT" ? "Never attributed until resolved" : "Raw ID, not attributed to a person"}</span>
      </span>
    );
  }
  return (
    <span className="min-w-0">
      <span className="block font-medium text-dt-text-primary">{r.employee_name ?? "Team member"}</span>
      <span className="block text-xs text-dt-text-secondary">BHR ID {r.bamboohr_id}{r.employee_number ? ` · EMP ${r.employee_number}` : ""} · ZK {r.zk_emp_codes.join(", ")}</span>
    </span>
  );
}

function Span({ r }: { r: DailyRow }) {
  return r.recorded_span_minutes === null
    ? <span className="text-dt-text-secondary" title={RECORDED_SPAN_HELP}>—</span>
    : <span className="tabular-nums" title={RECORDED_SPAN_HELP}>{formatRecordedSpan(r.recorded_span_minutes)}</span>;
}

function Review({ r }: { r: DailyRow }) {
  const rv = r.review;
  const earlier = r.earlier_code_cases ?? [];
  return (
    <span className="flex flex-wrap items-center gap-1">
      {r.single && <ToneBadge tone="neutral">Single Recorded Fingerprint</ToneBadge>}
      {rv && <ToneBadge tone={STATUS_TONE[rv.status]}>{STATUS_LABEL[rv.status]}</ToneBadge>}
      {(rv?.stale || earlier.some((c) => c.stale)) && <ToneBadge tone="warning">Needs reassessment</ToneBadge>}
      {earlier.length > 0 && <span className="text-xs text-dt-text-secondary">{earlier.length} earlier case(s) on the raw ID</span>}
    </span>
  );
}

/** Whole identity-day fingerprints, loaded on demand through /activity (exact selection). */
function DayPunches({ r, siteId }: { r: DailyRow; siteId: string }) {
  const verified = r.mapping_state === "VERIFIED";
  const q = useQuery({
    queryKey: ["onsite-activity", "daily-punches", siteId, r.identity_key, r.local_date],
    queryFn: () => getActivity({ site_id: siteId, date_from: r.local_date, date_to: r.local_date, sort: "time", page_size: 200,
      mapping: verified ? "verified" : r.mapping_state === "CONFLICT" ? "conflict" : "unverified",
      ...(verified ? { bamboohr_id: r.bamboohr_id ?? undefined } : { emp_code: r.emp_code }) }),
  });
  if (q.isLoading) return <SkeletonRows rows={2} label="Loading fingerprints…" />;
  if (!q.data) return <ErrorState onRetry={() => q.refetch()} />;
  const items = verified ? q.data.items : q.data.items.filter((e) => e.emp_code === r.emp_code);
  return (
    <ol className="flex flex-wrap gap-2 text-xs" aria-label={`Recorded fingerprints of ${identityLabel(r)} on ${r.local_date}`}>
      {items.map((e) => (
        <li key={e.event_id ?? e.local_time} className="rounded-full border border-dt-border bg-dt-surface px-2 py-0.5">
          <span className="font-medium tabular-nums">{localTime(e.local_time)}</span>{" "}
          <span className="text-dt-text-secondary">{e.punch_sequence ? SEQUENCE_LABEL[e.punch_sequence] : ""} · {e.punch_position} of {e.punches_in_day}{e.terminal ? ` · ${e.terminal}` : ""}</span>
        </li>
      ))}
    </ol>
  );
}

/** Identity-day counts per mapping status. Each card filters the Daily summary to that
 *  status (the summary always counts the filters without the mapping filter, so the four
 *  totals never change while switching). Clicking the active status returns to All. */
function SummaryCards({ s, value, onChange }: { s: DailySummary; value: MappingFilter; onChange: (v: MappingFilter) => void }) {
  const items: { key: MappingFilter; label: string; value: number; sub: string; bar?: string }[] = [
    { key: "all", label: "Identity-days", value: s.identity_days, sub: `${fmtNum(s.punches)} recorded fingerprints` },
    { key: "verified", label: "Verified", value: s.verified_identity_days, sub: `${fmtNum(s.verified_punches)} fingerprints`, bar: MAPPING_STATE.VERIFIED.bar },
    { key: "unmapped", label: "Unmapped", value: s.unmapped_identity_days, sub: `${fmtNum(s.unmapped_punches)} fingerprints`, bar: MAPPING_STATE.UNMAPPED.bar },
    { key: "conflict", label: "Mapping conflict", value: s.conflict_identity_days, sub: `${fmtNum(s.conflict_punches)} fingerprints`, bar: MAPPING_STATE.CONFLICT.bar },
  ];
  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4" role="group" aria-label="Identity-days by mapping status">
      {items.map((i) => {
        const active = value === i.key;
        return (
          <button key={i.key} type="button" aria-pressed={active}
            aria-label={`${i.label}: ${fmtNum(i.value)} identity-days, ${i.sub}. ${active && i.key !== "all" ? "Showing only these. Select again to show all." : `Show ${i.key === "all" ? "all identity-days" : `only ${i.label.toLowerCase()} identity-days`}.`}`}
            onClick={() => onChange(active && i.key !== "all" ? "all" : i.key)}
            className={cx("rounded-xl border bg-dt-surface p-3 text-left transition-colors hover:border-dt-orange/60 hover:bg-dt-surface-warm/60",
              focusRing, active ? "border-dt-burnt-orange ring-1 ring-dt-burnt-orange/40" : "border-dt-border")}>
            <span className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-dt-text-secondary">
              {i.bar && <span aria-hidden className={cx("size-2.5 rounded-sm", i.bar)} />}{i.label}
            </span>
            <span className="mt-1 block text-2xl font-semibold tabular-nums text-dt-text-primary">{fmtNum(i.value)}</span>
            <span className="block text-xs text-dt-text-secondary">{i.sub}</span>
          </button>
        );
      })}
    </div>
  );
}

export function DailyView({ filters, sort, onSort, page, pageSize, onPage, onPageSize, onEvents, today, onMapping }: {
  filters: DailyFilters; sort: string; onSort: (s: string) => void; page: number; pageSize: number;
  onPage: (p: number) => void; onPageSize: (n: number) => void; onEvents: (r: DailyRow) => void; today: string;
  /** Selects a mapping status (and returns to page 1), keeping every other filter. */
  onMapping: (v: MappingFilter) => void;
}) {
  const query = useQuery({ queryKey: ["onsite-activity-daily", filters, sort, page, pageSize],
    queryFn: () => getDailyActivity({ ...filters, sort, page, page_size: pageSize }), ...liveQuery });
  const [review, setReview] = useState<ReviewTarget | null>(null);
  const canManage = Boolean(query.data?.can_manage_reviews);
  const openReview = (r: DailyRow) => setReview({ siteId: filters.site_id, date: r.local_date, label: identityLabel(r), single: r.single,
    ...(r.mapping_state === "VERIFIED" ? { bamboohrId: r.bamboohr_id } : { zkEmpCode: r.emp_code }) });
  const reviewButton = (r: DailyRow) => (
    <button type="button" className={cx(buttonClass("ghost"), focusRing)} onClick={() => openReview(r)}>
      {canManage ? "Review…" : r.review ? "View case" : "View day"}
    </button>
  );

  if (query.isLoading) return <SkeletonRows label="Loading daily fingerprint activity…" />;
  if (!query.data) return <ErrorState onRetry={() => query.refetch()} />;
  const d = query.data;
  return (
    <div className="space-y-3">
      <SummaryCards s={d.summary} value={filters.mapping} onChange={onMapping} />
      {d.total === 0 ? (
        <EmptyPanel icon={CalendarSearch} title="No recorded fingerprints match" description="Try another period, mapping status or filter." />
      ) : (
        <>
          <DataView caption="Daily fingerprint activity by identity" rows={d.items} rowKey={(r) => `${r.local_date}-${r.identity_key}`}
            rowLabel={(r) => `${identityLabel(r)} on ${r.local_date}`} sort={sort} onSort={onSort}
            columns={[
              { key: "identity", header: "Identity", sort: "identity", cell: (r) => <Identity r={r} /> },
              { key: "status", header: "Status", minWidth: "2xl", cell: (r) => <MappingStateBadge state={r.mapping_state} /> },
              { key: "date", header: "Date", sort: "date", cell: (r) => r.local_date === today ? "Today" : fmtDay(r.local_date) },
              { key: "first", header: "First Recorded Fingerprint", sort: "first", cell: (r) => <span className="tabular-nums">{localTime(r.first_fingerprint_local)}</span> },
              { key: "last", header: "Last Recorded Fingerprint", sort: "last", cell: (r) => <span className="tabular-nums">{r.single ? "—" : localTime(r.last_fingerprint_local)}</span> },
              { key: "span", header: "Recorded Span", sort: "span", help: RECORDED_SPAN_HELP, cell: (r) => <Span r={r} /> },
              { key: "punches", header: "Punches", sort: "punches", align: "right", nowrap: true, cell: (r) => fmtNum(r.punch_count) },
              { key: "review", header: "Review", minWidth: "2xl", cell: (r) => <Review r={r} /> },
              { key: "act", header: <span className="sr-only">Actions</span>, nowrap: true, minWidth: "xl", cell: reviewButton },
            ]}
            card={(r) => (
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <Identity r={r} />
                  <MappingStateBadge state={r.mapping_state} />
                </div>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                  <div><dt className="text-xs text-dt-text-secondary">Date</dt><dd>{fmtDay(r.local_date)}</dd></div>
                  <div><dt className="text-xs text-dt-text-secondary">Punches</dt><dd className="tabular-nums">{r.punch_count}</dd></div>
                  <div><dt className="text-xs text-dt-text-secondary">First recorded fingerprint</dt><dd className="tabular-nums">{localTime(r.first_fingerprint_local)}</dd></div>
                  <div><dt className="text-xs text-dt-text-secondary">Last recorded fingerprint</dt><dd className="tabular-nums">{r.single ? "—" : localTime(r.last_fingerprint_local)}</dd></div>
                  <div className="col-span-2"><dt className="text-xs text-dt-text-secondary">Recorded Span</dt><dd><Span r={r} /></dd></div>
                </dl>
                <Review r={r} />
                <div>{reviewButton(r)}</div>
              </div>
            )}
            detail={(r) => (
              <div className="space-y-2">
                <DayPunches r={r} siteId={filters.site_id} />
                <p className="text-xs text-dt-text-secondary">Recorded at the entry-side reader. The last recorded fingerprint is not an exit; Recorded Span is not time on premises or hours worked.</p>
                <div className="flex flex-wrap gap-2">
                  {reviewButton(r)}
                  <button type="button" className={buttonClass("ghost")} onClick={() => onEvents(r)}>Show these events in the Events view</button>
                </div>
              </div>
            )} />
          <Pager page={page} pageSize={pageSize} total={d.total} onPage={onPage} onPageSize={onPageSize} busy={query.isFetching} noun="identity-day" />
        </>
      )}
      {review && <AttendanceReviewDialog target={review} onClose={() => setReview(null)} />}
    </div>
  );
}
