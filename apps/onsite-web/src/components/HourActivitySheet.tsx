"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { ArrowLeft, ChevronLeft, ChevronRight, Clock, ExternalLink, X } from "lucide-react";
import { getActivity, type ActivityEvent } from "@/lib/dashboard";
import { useDialogLayer } from "@/lib/dialog-stack";
import { localTime } from "@/lib/flags";
import { liveQuery } from "@/lib/live-refresh";
import { parsePageSize, rememberPageSize, storedPageSize } from "@/lib/page-size";
import { dayCount, fmtDay, fmtNum, isSingleDay, type Period } from "@/lib/period";
import { hrefWith } from "@/lib/url-state";
import { DataView, Facts } from "./DataView";
import { FlagChips, MappingBadge } from "./FlagChips";
import { buttonClass, cx, EmployeeRefCell, EmptyPanel, focusRing, Pager, SkeletonRows } from "./kit";
import { useSite } from "./SiteContext";

const hh = (h: number) => String(h).padStart(2, "0");

/** The recorded events behind one bar of "Activity by hour of day": the
 *  site-local hour [hh:00:00, hh+1:00:00) on every date of the period,
 *  fetched from the Activity API (server-side, paged). Opening an employee
 *  hands over to the shared employee profile. */
export function HourActivitySheet({ period, hour, employees, onHour, onClose, onOpenEmployee }: {
  period: Period; hour: number; employees: number | null; onHour: (h: number) => void;
  onClose: () => void; onOpenEmployee: (code: string) => void;
}) {
  const { site } = useSite();
  const closeRef = useRef<HTMLButtonElement>(null);
  useDialogLayer(onClose, closeRef);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(() => parsePageSize(storedPageSize("hour")));
  const [lastHour, setLastHour] = useState(hour);
  if (lastHour !== hour) { // a different hour starts at its first page
    setLastHour(hour);
    setPage(1);
  }
  const params = { site_id: site.site_id, date_from: period.from, date_to: period.to, hour, sort: "time", page, page_size: size };
  const query = useQuery({ queryKey: ["onsite-activity", params], queryFn: () => getActivity(params), ...liveQuery });
  const single = isSingleDay(period);
  const range = `${hh(hour)}:00–${hh(hour)}:59:59`;
  const when = single ? fmtDay(period.from, true) : `${fmtDay(period.from)} – ${fmtDay(period.to, true)}`;
  const activityHref = hrefWith("/activity", { from: period.from, to: period.to, hour, sort: "time" });

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-labelledby="hour-sheet-title">
      <button type="button" aria-label="Close hour detail" tabIndex={-1} onClick={onClose} className="absolute inset-0 hidden bg-black/30 lg:block" />
      <div className="relative flex h-full w-full flex-col bg-dt-background shadow-2xl lg:max-w-3xl">
        <header className="sticky top-0 z-10 border-b border-dt-border bg-dt-surface px-4 py-3 sm:px-6">
          <div className="flex items-start gap-3">
            <button ref={closeRef} type="button" onClick={onClose} aria-label="Back"
              className={cx("-ml-1 grid size-10 shrink-0 place-items-center rounded-lg text-dt-text-secondary hover:bg-dt-surface-warm lg:hidden", focusRing)}>
              <ArrowLeft className="size-5" aria-hidden />
            </button>
            <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-dt-cream text-dt-burnt-orange"><Clock className="size-5" aria-hidden /></span>
            <div className="min-w-0 flex-1">
              <h2 id="hour-sheet-title" className="text-lg font-semibold text-dt-text-primary">
                {range} <span className="text-sm font-normal text-dt-text-secondary">{site.time_zone ?? ""}</span>
              </h2>
              <p className="text-sm text-dt-text-secondary">{site.name} · {when}</p>
              {!single && (
                <p className="mt-1 text-xs text-dt-burnt-orange">Combined across {dayCount(period)} days — this hour on every date in the period.</p>
              )}
            </div>
            <button type="button" onClick={onClose} aria-label="Close"
              className={cx("hidden size-10 shrink-0 place-items-center rounded-lg text-dt-text-secondary hover:bg-dt-surface-warm lg:grid", focusRing)}>
              <X className="size-5" aria-hidden />
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <Facts cols={2} items={[["Activity events", query.data ? fmtNum(query.data.total) : "…"],
              ["Employees with activity", employees === null ? "—" : fmtNum(employees)]]} />
            <div className="flex flex-wrap items-center gap-1">
              <button type="button" aria-label="Previous hour" disabled={hour <= 0} onClick={() => onHour(hour - 1)}
                className={cx(buttonClass("secondary"), "px-2 disabled:opacity-40")}><ChevronLeft className="size-4" aria-hidden /></button>
              <button type="button" aria-label="Next hour" disabled={hour >= 23} onClick={() => onHour(hour + 1)}
                className={cx(buttonClass("secondary"), "px-2 disabled:opacity-40")}><ChevronRight className="size-4" aria-hidden /></button>
              <Link href={activityHref} className={buttonClass("ghost")}>View in Activity <ExternalLink className="size-3.5" aria-hidden /></Link>
            </div>
          </div>
        </header>

        <div className="dt-scrollbar flex-1 overflow-y-auto px-4 py-4 sm:px-6">
          {query.isLoading ? <SkeletonRows rows={5} label="Loading events for this hour…" /> : !query.data ? <ErrorState onRetry={() => query.refetch()} /> :
            query.data.total === 0 ? (
              <EmptyPanel icon={Clock} title="No activity recorded in this hour"
                description={`No terminal activity was recorded between ${hh(hour)}:00 and ${hh(hour)}:59 ${single ? `on ${fmtDay(period.from)}` : "on any day in this period"}. This is not an absence record.`} />
            ) : (
              <>
                <DataView<ActivityEvent> caption={`Recorded events, ${range}, ${when}`} rows={query.data.items}
                  rowKey={(e) => e.event_id ?? `${e.emp_code}-${e.local_time}`} rowLabel={(e) => e.employee_name ?? e.emp_code}
                  onRowClick={(e) => onOpenEmployee(e.bamboohr_id ?? "")}
                  columns={[
                    { key: "emp", header: "Employee", cell: (e) => <EmployeeRefCell r={e} meta={e.department ?? undefined} size="sm" /> },
                    { key: "time", header: "Recorded", cell: (e) => (
                      <span className="whitespace-nowrap tabular-nums"><span className="font-medium">{localTime(e.local_time)}</span>
                        {!single && <span className="ml-1 text-xs text-dt-text-secondary">{fmtDay(e.local_date)}</span>}</span>
                    ) },
                    { key: "term", header: "Terminal", cell: (e) => e.terminal ?? "—" },
                    { key: "id", header: "Mapping Status", minWidth: "lg", cell: (e) => <MappingBadge status={e.mapping_status} cls={e.identity_class} /> },
                    { key: "flags", header: "Review", cell: (e) => <FlagChips flags={e.review_flags ?? []} /> },
                  ]}
                  card={(e) => (
                    <div className="space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <EmployeeRefCell r={e} meta={e.department ?? undefined} size="sm" />
                        <span className="shrink-0 text-right tabular-nums">
                          <span className="block font-semibold text-dt-text-primary">{localTime(e.local_time)}</span>
                          {!single && <span className="block text-xs text-dt-text-secondary">{fmtDay(e.local_date)}</span>}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-dt-text-secondary">
                        <span>{e.terminal ?? "Unknown terminal"}</span>
                        <MappingBadge status={e.mapping_status} cls={e.identity_class} />
                      </div>
                      {(e.review_flags ?? []).length > 0 && <FlagChips flags={e.review_flags ?? []} />}
                    </div>
                  )} />
                <Pager page={page} pageSize={size} total={query.data.total} noun="event" busy={query.isFetching} onPage={setPage}
                  onPageSize={(n) => { rememberPageSize("hour", n); setSize(n); setPage(1); }} />
              </>
            )}
        </div>
      </div>
    </div>
  );
}
