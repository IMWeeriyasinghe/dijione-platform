"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ErrorState } from "@dijione/design-system";
import { AlertTriangle, ArrowLeft, CalendarDays, ExternalLink, X } from "lucide-react";
import { getEmployee, type ActivityEvent, type DayActivity, type ReviewFlag } from "@/lib/dashboard";
import { addDays, FLAG_HELP, FLAG_LABEL, formatSpan, localTime } from "@/lib/flags";
import { liveQuery } from "@/lib/live-refresh";
import { eachDay, fmtDay, fmtNum, fmtPeriod, fmtShortDay, type Period } from "@/lib/period";
import { hrefWith } from "@/lib/url-state";
import { BarChart } from "./charts";
import { DataView, Facts } from "./DataView";
import { FlagChips, IdentityBadge } from "./FlagChips";
import { cx, EmptyPanel, focusRing, InfoTip, Initials, Panel, Segmented, Skeleton } from "./kit";
import { useSite } from "./SiteContext";
import { ToneBadge } from "./ToneBadge";

type Tab = "overview" | "days" | "flags";
const SPAN_HELP = "Time between the first and latest recorded activity on a day. It is not worked hours.";

/** Employee activity profile: a wide side panel on large screens and a
 *  full-screen sheet on small ones. Keyboard: focus moves into the panel,
 *  Escape closes, focus returns to the opener. */
export function EmployeeProfile({ code, to, onClose }: { code: string; to: string; onClose: () => void }) {
  const { site } = useSite();
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const period: Period = { from: addDays(to, -(Number(days) - 1)), to };
  const [tab, setTab] = useState<Tab>("overview");
  const [day, setDay] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  const query = useQuery({
    queryKey: ["onsite-employee", site.site_id, code, period.from, period.to],
    queryFn: () => getEmployee(code, { site_id: site.site_id, date_from: period.from, date_to: period.to }),
    ...liveQuery,
  });

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCloseRef.current(); };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      opener?.focus?.();
    };
  }, []);

  const data = query.data;
  const byDay = useMemo(() => new Map((data?.days ?? []).map((d) => [d.local_date, d])), [data]);
  const eventsByDay = useMemo(() => {
    const m = new Map<string, ActivityEvent[]>();
    for (const e of data?.events ?? []) m.set(e.local_date, [...(m.get(e.local_date) ?? []), e]);
    for (const list of m.values()) list.sort((a, b) => a.local_time.localeCompare(b.local_time));
    return m;
  }, [data]);
  const selected = day ?? data?.days[0]?.local_date ?? null;
  const flagged = (data?.days ?? []).filter((d) => d.flags.length);
  const name = data?.profile.employee_name ?? null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-labelledby="employee-profile-title">
      <button type="button" aria-label="Close employee profile" tabIndex={-1} onClick={onClose}
        className="absolute inset-0 hidden bg-black/30 motion-safe:transition-opacity lg:block" />
      <div className="relative flex h-full w-full flex-col bg-dt-background shadow-2xl lg:max-w-4xl">
        <header className="sticky top-0 z-10 border-b border-dt-border bg-dt-surface px-4 py-3 sm:px-6">
          <div className="flex items-start gap-3">
            <button ref={closeRef} type="button" onClick={onClose} aria-label="Back"
              className={cx("-ml-1 grid size-10 shrink-0 place-items-center rounded-lg text-dt-text-secondary hover:bg-dt-surface-warm lg:hidden", focusRing)}>
              <ArrowLeft className="size-5" aria-hidden />
            </button>
            <Initials name={name} code={code} size="lg" />
            <div className="min-w-0 flex-1">
              <h2 id="employee-profile-title" className="truncate text-lg font-semibold text-dt-text-primary">{name ?? "Unmatched code"}</h2>
              <p className="text-sm text-dt-text-secondary">
                <span className="font-mono">Employee Number {code}</span>
                {data?.profile.department && <> · {data.profile.department}</>}
                {data?.profile.job_title && <span className="hidden sm:inline"> · {data.profile.job_title}</span>}
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                {data && <IdentityBadge cls={data.profile.identity_class} />}
                {data?.profile.employment_status && (
                  <ToneBadge tone={data.profile.employment_status.toLowerCase() === "active" ? "success" : "neutral"}>{data.profile.employment_status}</ToneBadge>
                )}
                {data && data.profile.match_count > 1 && <ToneBadge tone="danger">{data.profile.match_count} directory records share this number</ToneBadge>}
              </div>
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
            <div className="space-y-3" role="status" aria-label="Loading employee activity">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-16" />)}</div>
              <Skeleton className="h-48 w-full" />
            </div>
          ) : !data ? (
            <ErrorState onRetry={() => query.refetch()} />
          ) : (
            <>
              {!data.directory_available && (
                <p className="mb-3 text-sm text-dt-burnt-orange">Employee details are unavailable right now — showing the Employee Code only.</p>
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
                      empty="No activity recorded for this employee in the selected period." />
                  </Panel>
                  {selected && <DayDetail day={byDay.get(selected) ?? null} date={selected} events={eventsByDay.get(selected) ?? []} code={code} />}
                </div>
              )}
              {tab === "days" && (
                <div id="panel-days" role="tabpanel" aria-labelledby="tab-days">
                  {data.days.length === 0 ? (
                    <EmptyPanel icon={CalendarDays} title="No activity recorded" description="No activity is recorded for this employee in the selected period. This is not an absence record." />
                  ) : (
                    <DataView caption="Daily activity" rows={data.days} rowKey={(d) => d.local_date} rowLabel={(d) => fmtDay(d.local_date)}
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
                      detail={(d) => <EventList events={eventsByDay.get(d.local_date) ?? []} />}
                    />
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
                                  Events: {(eventsByDay.get(d.local_date) ?? []).map((e) => localTime(e.local_time)).join(", ") || `${d.punch_count}`}
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

function DayDetail({ day, date, events, code }: { day: DayActivity | null; date: string; events: ActivityEvent[]; code: string }) {
  return (
    <Panel title={fmtDay(date, true)} subtitle={day ? `${day.punch_count} recorded events` : "No activity recorded on this day"}
      action={day ? <Link href={hrefWith("/activity", { emp: code, from: date, to: date })} className="inline-flex min-h-9 items-center text-xs font-medium text-dt-burnt-orange">Open in Activity</Link> : undefined}>
      {day ? (
        <div className="space-y-3">
          <Facts cols={4} items={[["First", localTime(day.first_activity_local)], ["Latest", localTime(day.latest_activity_local)],
            [<span key="s" className="inline-flex items-center gap-1">Activity span <InfoTip text={SPAN_HELP} /></span>, formatSpan(day.span_minutes)],
            ["Terminals", day.terminal_names.join(", ") || "—"]]} />
          <FlagChips flags={day.flags} empty="No review flags" />
          <EventList events={events} />
        </div>
      ) : <p className="text-sm text-dt-text-secondary">Nothing recorded. This is not an absence record.</p>}
    </Panel>
  );
}

function EventList({ events }: { events: ActivityEvent[] }) {
  if (!events.length) return <p className="text-sm text-dt-text-secondary">Event details are not available for this day.</p>;
  return (
    <ol className="relative space-y-2 border-l-2 border-dt-border pl-4" aria-label="Recorded events">
      {events.map((e, i) => (
        <li key={e.event_id ?? `${e.local_time}-${i}`} className="relative text-sm">
          <span aria-hidden className="absolute -left-[1.4rem] top-1.5 size-2.5 rounded-full border-2 border-dt-surface bg-dt-orange" />
          <span className="font-medium tabular-nums text-dt-text-primary">{localTime(e.local_time)}</span>
          <span className="text-dt-text-secondary"> · {e.terminal ?? "Unknown terminal"}{e.area ? ` · ${e.area}` : ""}</span>
          <span className="ml-1 font-mono text-xs text-dt-text-secondary" title="Raw device state, recorded as-is (not interpreted)">state {e.punch_state_raw ?? "—"}</span>
        </li>
      ))}
    </ol>
  );
}
