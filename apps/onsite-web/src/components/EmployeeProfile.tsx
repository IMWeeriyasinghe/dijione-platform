"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { AlertTriangle, ArrowLeft, CalendarDays, ExternalLink, X } from "lucide-react";
import { getActivity, getEmployee, type ActivityEvent, type DayActivity, type ReviewFlag } from "@/lib/dashboard";
import { addDays, FLAG_HELP, FLAG_LABEL, formatSpan, localTime } from "@/lib/flags";
import { useDialogLayer } from "@/lib/dialog-stack";
import { liveQuery } from "@/lib/live-refresh";
import { eachDay, fmtDay, fmtNum, fmtPeriod, fmtShortDay, type Period } from "@/lib/period";
import { hrefWith } from "@/lib/url-state";
import { BarChart } from "./charts";
import { DataView, Facts } from "./DataView";
import { FlagChips, MappingBadge } from "./FlagChips";
import { cx, EmptyPanel, focusRing, InfoTip, Initials, Pager, Panel, Segmented, Skeleton } from "./kit";
import { useSite } from "./SiteContext";
import { ToneBadge } from "./ToneBadge";

type Tab = "overview" | "days" | "flags";
const SPAN_HELP = "Time between the first and latest recorded activity on a day. It is not worked hours.";

/** Team Member activity profile of a VERIFIED team member, addressed by BHR
 *  Employee ID (``code``): attendance from every ZKBioTime ID mapped to them,
 *  each only inside its verified period. A wide side panel on large screens
 *  and a full-screen sheet on small ones. Keyboard: focus moves into the
 *  panel, Escape closes, focus returns to the opener. */
export function EmployeeProfile({ code, to, onClose }: { code: string; to: string; onClose: () => void }) {
  const { site } = useSite();
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const period: Period = { from: addDays(to, -(Number(days) - 1)), to };
  const [tab, setTab] = useState<Tab>("overview");
  const [day, setDay] = useState<string | null>(null);
  const [daysPage, setDaysPage] = useState(1);
  const [daysSize, setDaysSize] = useState(10);
  const closeRef = useRef<HTMLButtonElement>(null);
  useDialogLayer(onClose, closeRef);

  // Essentials + the selected period's daily summary only; raw events are
  // fetched per day when shown (DayEvents).
  const query = useQuery({
    queryKey: ["onsite-employee", site.site_id, code, period.from, period.to],
    queryFn: () => getEmployee(code, { site_id: site.site_id, date_from: period.from, date_to: period.to, include_events: false }),
    ...liveQuery,
  });

  const data = query.data;
  const byDay = useMemo(() => new Map((data?.days ?? []).map((d) => [d.local_date, d])), [data]);
  const selected = day ?? data?.days[0]?.local_date ?? null;
  const flagged = (data?.days ?? []).filter((d) => d.flags.length);
  const name = data?.profile.employee_name ?? null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-labelledby="employee-profile-title">
      <button type="button" aria-label="Close team member profile" tabIndex={-1} onClick={onClose}
        className="absolute inset-0 hidden bg-black/30 motion-safe:transition-opacity lg:block" />
      <div className="relative flex h-full w-full flex-col bg-dt-background shadow-2xl lg:max-w-4xl">
        <header className="sticky top-0 z-10 border-b border-dt-border bg-dt-surface px-4 py-3 sm:px-6">
          <div className="flex items-start gap-3">
            <button ref={closeRef} type="button" onClick={onClose} aria-label="Back"
              className={cx("-ml-1 grid size-10 shrink-0 place-items-center rounded-lg text-dt-text-secondary hover:bg-dt-surface-warm lg:hidden", focusRing)}>
              <ArrowLeft className="size-5" aria-hidden />
            </button>
            <Initials name={name} code={code} size="lg" photo={data?.profile.has_photo} bhrId={data?.profile.bamboohr_id ?? null}
              alt={name ? `Profile photo of ${name}` : undefined} />
            <div className="min-w-0 flex-1">
              <h2 id="employee-profile-title" className="truncate text-lg font-semibold text-dt-text-primary">{name ?? "Name unavailable"}</h2>
              <p className="text-sm text-dt-text-secondary">
                <span className="font-mono">BHR Employee ID {code}</span>
                {data?.profile.employee_number && <> · <span className="font-mono">EMP Number {data.profile.employee_number}</span></>}
                {data?.profile.department && <> · {data.profile.department}</>}
                {data?.profile.job_title && <span className="hidden sm:inline"> · {data.profile.job_title}</span>}
              </p>
              <p className="text-xs text-dt-text-secondary">
                ZKBioTime ID(s): <span className="font-mono">{(data?.profile.zk_emp_codes ?? []).join(", ") || "—"}</span>
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                {data && <MappingBadge status={data.profile.mapping_status} cls={data.profile.identity_class} />}
                {data?.profile.employment_status && (
                  <ToneBadge tone={data.profile.employment_status.toLowerCase() === "active" ? "success" : "neutral"}>{data.profile.employment_status}</ToneBadge>
                )}
              </div>
              {data?.mappings && data.mappings.length > 0 && (
                <ul className="mt-1.5 flex flex-wrap gap-1.5 text-xs text-dt-text-secondary" aria-label="Verified ZKBioTime ID periods">
                  {data.mappings.map((m) => (
                    <li key={m.mapping_id} className="rounded-md border border-dt-border px-1.5 py-0.5">
                      <span className="font-mono">{m.zk_emp_code}</span>: {m.valid_from} → {m.valid_to ?? "open"}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <button type="button" onClick={onClose} aria-label="Close"
              className={cx("hidden size-10 shrink-0 place-items-center rounded-lg text-dt-text-secondary hover:bg-dt-surface-warm lg:grid", focusRing)}>
              <X className="size-5" aria-hidden />
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <div role="tablist" aria-label="Employee profile sections" className="flex gap-1">
              {([["overview", "Overview", "Overview"], ["days", "Daily activity", "Days"], ["flags", "Review flags", "Flags"]] as [Tab, string, string][]).map(([t, label, short]) => (
                <button key={t} type="button" role="tab" aria-selected={tab === t} id={`tab-${t}`} aria-controls={`panel-${t}`} onClick={() => setTab(t)}
                  className={cx("min-h-9 rounded-md px-3 text-sm font-medium", focusRing,
                    tab === t ? "bg-dt-cream text-dt-burnt-orange" : "text-dt-text-secondary hover:bg-dt-surface-warm")}>
                  <span className="hidden sm:inline">{label}</span><span className="sm:hidden">{short}</span>
                  {data && t !== "overview" && <span className="ml-1 tabular-nums">({t === "days" ? data.days.length : flagged.length})</span>}
                </button>
              ))}
            </div>
            <Segmented size="sm" label="Profile period" value={days} onChange={(v) => { setDays(v); setDay(null); }}
              options={[{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "90", label: "90 days" }]} />
          </div>
          <p className="mt-1 text-xs text-dt-text-secondary">{fmtPeriod(period, site.today)} · {site.name} · site-local time</p>
        </header>

        <div className="dt-scrollbar flex-1 overflow-y-auto px-4 py-4 sm:px-6">
          {query.isLoading ? (
            <div className="space-y-3" role="status" aria-label="Loading team member activity">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-16" />)}</div>
              <Skeleton className="h-48 w-full" />
            </div>
          ) : !data ? (
            <ErrorState onRetry={() => query.refetch()} />
          ) : (
            <>
              {!data.directory_available && (
                <p className="mb-3 text-sm text-dt-burnt-orange">Team member details are unavailable right now — verified attendance is shown without the name.</p>
              )}
              {tab === "overview" && (
                <div id="panel-overview" role="tabpanel" aria-labelledby="tab-overview" className="space-y-4">
                  <Summary days={data.days} events={data.summary.events} flags={data.summary.review_flags} />
                  <Panel title="Events per day" subtitle={`Recorded activity events · ${fmtPeriod(period)} · select a day to inspect it`}>
                    <BarChart measure="events" summary={`Activity events per day for ${name ?? code}, ${period.from} to ${period.to}`}
                      selected={selected} onSelect={setDay} tickEvery={days === "7" ? [1, 1] : days === "30" ? [7, 5] : [21, 14]}
                      data={eachDay(period).map((d) => ({ key: d, value: byDay.get(d)?.punch_count ?? 0, label: fmtDay(d, true),
                        tick: days === "7" ? fmtDay(d).slice(0, 3) : fmtShortDay(d),
                        note: byDay.get(d)?.flags.length ? `${byDay.get(d)!.flags.length} review flag(s)` : undefined }))}
                      empty="No activity recorded for this team member in the selected period." />
                  </Panel>
                  {selected && <DayDetail day={byDay.get(selected) ?? null} date={selected} code={code} />}
                </div>
              )}
              {tab === "days" && (
                <div id="panel-days" role="tabpanel" aria-labelledby="tab-days">
                  {data.days.length === 0 ? (
                    <EmptyPanel icon={CalendarDays} title="No activity recorded" description="No activity is recorded for this team member in the selected period. This is not an absence record." />
                  ) : (
                    <DataView caption="Daily activity" rows={data.days.slice((daysPage - 1) * daysSize, daysPage * daysSize)} rowKey={(d) => d.local_date} rowLabel={(d) => fmtDay(d.local_date)}
                      columns={[
                        { key: "date", header: "Date", cell: (d) => <span className="whitespace-nowrap font-medium">{fmtDay(d.local_date, true)}</span> },
                        { key: "first", header: "First", cell: (d) => localTime(d.first_activity_local) },
                        { key: "latest", header: "Latest", cell: (d) => localTime(d.latest_activity_local) },
                        { key: "count", header: "Events", align: "right", cell: (d) => d.punch_count },
                        { key: "span", header: <span className="inline-flex items-center gap-1">Activity span <InfoTip text={SPAN_HELP} /></span>, cell: (d) => formatSpan(d.span_minutes) },
                        { key: "terms", header: "Terminals", minWidth: "xl", cell: (d) => d.terminal_names.join(", ") || "—" },
                        { key: "flags", header: "Review", cell: (d) => <FlagChips flags={d.flags} /> },
                      ]}
                      card={(d) => (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-medium text-dt-text-primary">{fmtDay(d.local_date, true)}</span>
                            <span className="text-sm tabular-nums text-dt-text-secondary">{d.punch_count} events</span>
                          </div>
                          <Facts items={[["First", localTime(d.first_activity_local)], ["Latest", localTime(d.latest_activity_local)],
                            ["Activity span", formatSpan(d.span_minutes)], ["Terminals", d.terminal_names.join(", ") || "—"]]} />
                          <FlagChips flags={d.flags} empty="No review flags" />
                        </div>
                      )}
                      detail={(d) => <DayEvents code={code} date={d.local_date} />}
                    />
                  )}
                  {data.days.length > 0 && (
                    <Pager page={daysPage} pageSize={daysSize} total={data.days.length} noun="day"
                      onPage={setDaysPage} onPageSize={(n) => { setDaysSize(n); setDaysPage(1); }} />
                  )}
                </div>
              )}
              {tab === "flags" && (
                <div id="panel-flags" role="tabpanel" aria-labelledby="tab-flags" className="space-y-3">
                  <p className="text-sm text-dt-text-secondary">Review flags are prompts to take a closer look. They are not confirmed policy breaches.</p>
                  {flagged.length === 0 ? (
                    <EmptyPanel icon={AlertTriangle} title="No review flags" description="No recorded day in this period was flagged for review." />
                  ) : (
                    groupByFlag(flagged).map(([flag, list]) => (
                      <Panel key={flag} title={`${FLAG_LABEL[flag]} · ${list.length} day${list.length === 1 ? "" : "s"}`} subtitle={FLAG_HELP[flag]}>
                        <ul className="divide-y divide-dt-border/60">
                          {list.map((d) => (
                            <li key={d.local_date} className="flex flex-col gap-2 py-2 sm:flex-row sm:items-center sm:justify-between">
                              <div className="min-w-0">
                                <p className="font-medium text-dt-text-primary">{fmtDay(d.local_date, true)}</p>
                                <p className="text-xs text-dt-text-secondary">
                                  {d.punch_count} events · first {localTime(d.first_activity_local)} · latest {localTime(d.latest_activity_local)}
                                </p>
                              </div>
                              <Link href={hrefWith("/activity", { emp: code, from: d.local_date, to: d.local_date })}
                                className={cx("inline-flex min-h-9 items-center gap-1 text-sm font-medium text-dt-burnt-orange", focusRing)}>
                                View events <ExternalLink className="size-3.5" aria-hidden />
                              </Link>
                            </li>
                          ))}
                        </ul>
                      </Panel>
                    ))
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function groupByFlag(days: DayActivity[]): [ReviewFlag, DayActivity[]][] {
  const m = new Map<ReviewFlag, DayActivity[]>();
  for (const d of days) for (const f of d.flags) m.set(f, [...(m.get(f) ?? []), d]);
  return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
}

function Summary({ days, events, flags }: { days: DayActivity[]; events: number; flags: number }) {
  const oldest = days[days.length - 1];
  const newest = days[0];
  const items: [string, string, string?][] = [
    ["Activity days", fmtNum(days.length)],
    ["Total events", fmtNum(events)],
    ["Average per activity day", days.length ? (events / days.length).toFixed(1) : "—"],
    ["First recorded", oldest ? `${fmtShortDay(oldest.local_date)} ${localTime(oldest.first_activity_local)}` : "—", "Earliest recorded activity in this period"],
    ["Latest recorded", newest ? `${fmtShortDay(newest.local_date)} ${localTime(newest.latest_activity_local)}` : "—", "Most recent recorded activity in this period"],
    ["Review flags", fmtNum(flags)],
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {items.map(([label, value, title]) => (
        <div key={label} className="rounded-xl border border-dt-border bg-dt-surface px-3 py-2.5" title={title}>
          <dt className="text-xs text-dt-text-secondary">{label}</dt>
          <dd className="mt-0.5 text-lg font-semibold tabular-nums text-dt-text-primary">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function DayDetail({ day, date, code }: { day: DayActivity | null; date: string; code: string }) {
  return (
    <Panel title={fmtDay(date, true)} subtitle={day ? `${day.punch_count} recorded events` : "No activity recorded on this day"}
      action={day ? <Link href={hrefWith("/activity", { emp: code, from: date, to: date })} className="inline-flex min-h-9 items-center text-xs font-medium text-dt-burnt-orange">Open in Activity</Link> : undefined}>
      {day ? (
        <div className="space-y-3">
          <Facts cols={4} items={[["First", localTime(day.first_activity_local)], ["Latest", localTime(day.latest_activity_local)],
            [<span key="s" className="inline-flex items-center gap-1">Activity span <InfoTip text={SPAN_HELP} /></span>, formatSpan(day.span_minutes)],
            ["Terminals", day.terminal_names.join(", ") || "—"]]} />
          <FlagChips flags={day.flags} empty="No review flags" />
          <DayEvents code={code} date={date} />
        </div>
      ) : <p className="text-sm text-dt-text-secondary">Nothing recorded. This is not an absence record.</p>}
    </Panel>
  );
}

/** One day's recorded events, fetched only when shown (Activity API, paged,
 *  oldest first) — opening a profile never downloads the whole history. */
function DayEvents({ code, date }: { code: string; date: string }) {
  const { site } = useSite();
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(10);
  const params = { site_id: site.site_id, bamboohr_id: code, date_from: date, date_to: date, sort: "time", page, page_size: size };
  const query = useQuery({ queryKey: ["onsite-activity", params], queryFn: () => getActivity(params), ...liveQuery });
  if (query.isLoading) return <Skeleton className="h-16 w-full" />;
  if (!query.data) return <p className="text-sm text-dt-text-secondary">Events could not be loaded. <button type="button" className="underline" onClick={() => query.refetch()}>Retry</button></p>;
  const events = query.data.items;
  if (!events.length) return <p className="text-sm text-dt-text-secondary">No recorded events on this day.</p>;
  return (
    <div>
      <ol className="relative space-y-2 border-l-2 border-dt-border pl-4" aria-label="Recorded events">
        {events.map((e: ActivityEvent, i: number) => (
          <li key={e.event_id ?? `${e.local_time}-${i}`} className="relative text-sm">
            <span aria-hidden className="absolute left-[-1.4rem] top-1.5 size-2.5 rounded-full border-2 border-dt-surface bg-dt-orange" />
            <span className="font-medium tabular-nums text-dt-text-primary">{localTime(e.local_time)}</span>
            <span className="text-dt-text-secondary"> · {e.terminal ?? "Unknown terminal"}{e.area ? ` · ${e.area}` : ""}</span>
            <span className="ml-1 font-mono text-xs text-dt-text-secondary" title="Raw device state, recorded as-is (not interpreted)">state {e.punch_state_raw ?? "—"}</span>
          </li>
        ))}
      </ol>
      {query.data.total > size && (
        <Pager page={page} pageSize={size} total={query.data.total} noun="event" onPage={setPage} onPageSize={(n) => { setSize(n); setPage(1); }} />
      )}
    </div>
  );
}
