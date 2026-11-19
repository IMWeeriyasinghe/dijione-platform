"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { CheckCircle2, ExternalLink, SearchX } from "lucide-react";
import { DataView, Facts } from "@/components/DataView";
import { EmployeeProfile } from "@/components/EmployeeProfile";
import { AttendanceReviewDialog, type ReviewTarget } from "@/components/AttendanceReviewDialog";
import { ExportReportButton } from "@/components/ReportExportDialog";
import { ToneBadge } from "@/components/ToneBadge";
import { DepartmentSelect, IdentitySelect, PeriodControl, SearchField, SelectField, SiteSelect } from "@/components/FilterBar";
import { FlagChips } from "@/components/FlagChips";
import { FreshnessIndicator } from "@/components/FreshnessIndicator";
import { buttonClass, cx, EmployeeRefCell, EmptyPanel, FilterPanel, focusRing, Pager, PageTop, SkeletonRows, type Chip } from "@/components/kit";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { getExceptions, VIEWER_REVIEW_FLAGS, type ExceptionItem, type ReviewFlag } from "@/lib/dashboard";
import { addDays, DATA_QUALITY_FLAGS, FLAG_HELP, FLAG_LABEL, localTime } from "@/lib/flags";
import { formatRecordedSpan, IDENTITY_LABEL } from "@/lib/format";
import { REVIEW_STATUS_FILTERS, STATUS_LABEL, STATUS_TONE } from "@/lib/reviews";
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
  { value: "employee", label: "Team member (A-Z)" },
  { value: "-punch_count", label: "Most events first" },
];

function ExceptionsView() {
  const { site } = useSite();
  const [s, set] = useUrlState({ from: addDays(site.today, -6), to: site.today, flag: "", q: "", emp: "", dept: "", id: "", review: "", sort: "-date", page: "1", size: storedPageSize("exceptions"), open: "" });
  const page = Math.max(1, Number(s.page) || 1);
  const pageSize = parsePageSize(s.size);
  const [reviewing, setReviewing] = useState<ReviewTarget | null>(null);
  const filters = { site_id: site.site_id, date_from: s.from, date_to: s.to, flag: s.flag || undefined, q: s.q || undefined,
    emp_code: s.emp.trim() || undefined, department: s.dept || undefined, identity_class: s.id || undefined,
    review_status: s.review || undefined };
  const params = { ...filters, sort: s.sort, page, page_size: pageSize };
  const query = useQuery({ queryKey: ["onsite-exceptions", params], queryFn: () => getExceptions(params), ...liveQuery });
  const counts = query.data?.counts;
  const totalFlags = counts ? Object.values(counts).reduce((a, b) => a + b, 0) : 0;

  const paging = usePaging("exceptions", s, set, query.data?.total);
  const chips: Chip[] = [
    s.q && { key: "q", label: `Search: ${s.q}`, onClear: () => set({ q: "" }) },
    s.emp && { key: "emp", label: `ZKBioTime ID: ${s.emp}`, onClear: () => set({ emp: "" }) },
    s.dept && { key: "dept", label: s.dept, onClear: () => set({ dept: "" }) },
    s.id && { key: "id", label: IDENTITY_LABEL[s.id as IdentityClass] ?? s.id, onClear: () => set({ id: "" }) },
    s.flag && { key: "flag", label: FLAG_LABEL[s.flag as ReviewFlag], onClear: () => set({ flag: "" }) },
    s.review && { key: "review", label: `Review: ${REVIEW_STATUS_FILTERS.find((o) => o.value === s.review)?.label ?? s.review}`, onClear: () => set({ review: "" }) },
  ].filter(Boolean) as Chip[];
  const clearAll = () => set({ q: "", emp: "", dept: "", id: "", flag: "", review: "" });
  const canManage = Boolean(query.data?.can_manage_reviews);
  const openReview = (item: ExceptionItem) => setReviewing({ siteId: site.site_id, date: item.local_date, bamboohrId: item.bamboohr_id,
    label: item.employee_name ?? `BHR ID ${item.bamboohr_id}`, single: item.flags.includes("SINGLE_PUNCH") });
  const reviewCell = (item: ExceptionItem) => {
    const rv = item.review;
    return (
      <span className="flex flex-wrap items-center gap-1">
        {rv ? <ToneBadge tone={STATUS_TONE[rv.status]}>{STATUS_LABEL[rv.status]}</ToneBadge> : <span className="text-xs text-dt-text-secondary">Not reviewed</span>}
        {rv?.stale && <ToneBadge tone="warning">Needs reassessment</ToneBadge>}
        <button type="button" className={cx(buttonClass("ghost"), focusRing)} onClick={() => openReview(item)}>
          {canManage ? "Review…" : "View case"}
        </button>
      </span>
    );
  };

  const actions = (item: ExceptionItem) => (
    <div className="flex flex-wrap gap-2">
      <button type="button" className={buttonClass("secondary")} onClick={() => set({ open: item.bamboohr_id ?? "", page: s.page })}>Open team member profile</button>
      <Link href={hrefWith("/activity", { view: "events", emp: item.emp_code, from: item.local_date, to: item.local_date })} className={buttonClass("ghost")}>
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
        description="Team-member days that may need a closer look. Flags are prompts for review only. They are not confirmed policy breaches. A review case is an administrative record: fingerprint records are never changed, and a resolved case is not a verified duration."
        actions={<ExportReportButton departments={site.departments ?? []} terminals={site.terminals} context={{
          report: "exceptions", siteId: site.site_id, today: site.today, from: s.from, to: s.to, q: s.q, emp: s.emp, dept: s.dept, flag: s.flag }} />}>
        <div className="flex flex-wrap items-center gap-2">
          <SiteSelect />
          <PeriodControl value={{ from: s.from, to: s.to }} today={site.today} onChange={(p) => set({ from: p.from, to: p.to })} />
        </div>
        <FreshnessIndicator siteId={site.site_id} queries={[query]} />
      </PageTop>

      <div role="group" aria-label="Filter by review category" className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <CategoryTile active={!s.flag} label="All categories" count={totalFlags} help="Every review flag in the period (a team-member day can carry several)."
          onClick={() => set({ flag: "" })} loading={!counts} />
        {VIEWER_REVIEW_FLAGS.map((f) => (
          <CategoryTile key={f} active={s.flag === f} label={FLAG_LABEL[f]} count={counts?.[f] ?? 0} help={FLAG_HELP[f]} dataQuality={DATA_QUALITY_FLAGS.has(f)}
            onClick={() => set({ flag: s.flag === f ? "" : f })} loading={!counts} />
        ))}
      </div>

      <FilterPanel chips={chips} onClearAll={clearAll}>
        <SearchField label="Search name, BHR ID or EMP Number" value={s.q} onChange={(v) => set({ q: v })} />
        <SearchField label="ZKBioTime ID" value={s.emp} onChange={(v) => set({ emp: v })} placeholder="Exact ID" />
        <DepartmentSelect value={s.dept} onChange={(v) => set({ dept: v })} />
        <IdentitySelect value={s.id} onChange={(v) => set({ id: v })} />
        <SelectField label="Review status" value={s.review} onChange={(v) => set({ review: v })}
          options={REVIEW_STATUS_FILTERS.map((o) => ({ value: o.value, label: o.label }))} />
        <SelectField label="Sort by" value={s.sort} onChange={(v) => set({ sort: v })} options={SORTS} />
      </FilterPanel>

      <p className="text-sm text-dt-text-secondary">
        {fmtPeriod({ from: s.from, to: s.to }, site.today)}
        {query.data && <> · <span className="font-semibold text-dt-text-primary">{fmtNum(query.data.total)}</span> team-member days to review</>}
      </p>

      {query.isLoading ? <SkeletonRows label="Loading review queue…" /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> :
        query.data.total === 0 ? (
          chips.length ? (
            <EmptyPanel icon={SearchX} title="Nothing matches these filters" description="No flagged team-member day in this period matches the current filters."
              actions={<button type="button" className={buttonClass("secondary")} onClick={clearAll}>Clear filters</button>} />
          ) : (
            <EmptyPanel icon={CheckCircle2} title="Nothing needs review" description="No recorded day in this period was flagged for review." />
          )
        ) : (
          <>
            <DataView caption="Team-member days flagged for review" rows={query.data.items} rowKey={(i) => `${i.local_date}-${i.emp_code}`}
              rowLabel={(i) => `${i.employee_name ?? i.emp_code} on ${i.local_date}`} sort={s.sort} onSort={(v) => set({ sort: v })}
              columns={[
                { key: "date", header: "Date", sort: "date", cell: (i) => <span className="font-medium">{fmtDay(i.local_date, true)}</span> },
                { key: "emp", header: "Team Member", sort: "employee", cell: (i) => <EmployeeRefCell r={i} meta={i.department ?? undefined} size="sm" /> },
                { key: "flags", header: "Review flags", sort: "flags", cell: (i) => <FlagChips flags={i.flags} /> },
                { key: "times", header: "First · Last recorded fingerprint", minWidth: "lg", cell: (i) => <span className="tabular-nums">{localTime(i.first_activity_local)} · {i.punch_count === 1 ? "—" : localTime(i.latest_activity_local)}</span> },
                { key: "count", header: "Fingerprints", sort: "punch_count", align: "right", cell: (i) => i.punch_count },
                { key: "review", header: "Review", minWidth: "xl", cell: reviewCell },
                { key: "terms", header: "Terminals", minWidth: "2xl", cell: (i) => i.terminal_names.join(", ") || "—" },
              ]}
              card={(i) => (
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <EmployeeRefCell r={i} meta={i.department ?? undefined} size="sm" />
                    <span className="shrink-0 text-xs font-medium text-dt-text-primary">{fmtDay(i.local_date)}</span>
                  </div>
                  <FlagChips flags={i.flags} />
                  <Facts cols={3} items={[["First recorded fingerprint", localTime(i.first_activity_local)], ["Last recorded fingerprint", i.punch_count === 1 ? "—" : localTime(i.latest_activity_local)], ["Fingerprints", String(i.punch_count)]]} />
                  {reviewCell(i)}
                </div>
              )}
              detail={(i) => (
                <div className="space-y-3">
                  {reasons(i)}
                  <Facts cols={4} items={[["First recorded fingerprint", localTime(i.first_activity_local)], ["Last recorded fingerprint", i.punch_count === 1 ? "—" : localTime(i.latest_activity_local)],
                    ["Recorded Span", formatRecordedSpan(i.recorded_span_minutes ?? (i.punch_count > 1 ? i.span_minutes : null))], ["Terminals", i.terminal_names.join(", ") || "—"]]} />
                  {actions(i)}
                </div>
              )} />
            <Pager page={page} pageSize={pageSize} total={query.data.total} onPage={paging.onPage} onPageSize={paging.onPageSize} busy={query.isFetching} noun="team-member day" />
          </>
        )}
      {s.open && <EmployeeProfile code={s.open} to={s.to} onClose={() => set({ open: "", page: s.page })} />}
      {reviewing && <AttendanceReviewDialog target={reviewing} onClose={() => setReviewing(null)} />}
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
