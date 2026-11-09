"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Card, EmptyState, LoadingState, PageHeader, StatusBadge } from "@dijione/design-system";
import { Coffee, LogIn, LogOut, Play } from "lucide-react";
import { DayHeading, Notice, OfflineBanner, Page, QueryError, RequirePermission, SessionRow, TotalsCards } from "@/components/ui";
import type { Session, Today, WorkMode } from "@/lib/api";
import { ALL_WORK_MODES, duration, localDate, time, WORK_MODE_LABEL, type TimeFormat } from "@/lib/format";
import { hasPermission, PERM, useAtworkScope } from "@/lib/atwork-scope";
import { useAttendanceAction, useLiveStatus, useLiveToday, useOnline, usePolicy, useServerOffset, useTick } from "@/lib/hooks";

function liveTotals(session: Session, serverTime: string, serverNow: number) {
  const elapsed = Math.max(0, Math.floor((serverNow - new Date(serverTime).getTime()) / 1000));
  const onBreak = session.breaks.some((b) => b.ended_at === null);
  const gross = session.totals.gross_seconds + elapsed;
  const breaks = session.totals.break_seconds + (onBreak ? elapsed : 0);
  return { gross, breaks, net: Math.max(0, gross - breaks) };
}

function Timer({ label, seconds, large }: { label: string; seconds: number; large?: boolean }) {
  return (
    <div>
      <p className="text-sm text-dt-text-secondary">{label}</p>
      <p role="timer" aria-label={label} className={`font-mono font-semibold tabular-nums ${large ? "text-4xl sm:text-5xl" : "text-2xl"}`}>{duration(seconds)}</p>
    </div>
  );
}

type Timeline = { at: string; label: string };

function timeline(sessions: Session[]): Timeline[] {
  const items: Timeline[] = [];
  for (const s of sessions) {
    items.push({ at: s.check_in_at, label: `Checked in · ${WORK_MODE_LABEL[s.work_mode]}` });
    for (const b of s.breaks) {
      items.push({ at: b.started_at, label: "Break started" });
      if (b.ended_at) items.push({ at: b.ended_at, label: "Break ended" });
    }
    if (s.check_out_at) items.push({ at: s.check_out_at, label: "Checked out" });
  }
  return items.sort((a, b) => a.at.localeCompare(b.at));
}

function TodaySummary({ today, format, serverNow }: { today: Today; format: TimeFormat; serverNow: number }) {
  const completed = today.sessions.filter((s) => s.status === "COMPLETED");
  const events = timeline(today.sessions);
  const open = today.sessions.find((s) => s.status === "OPEN");
  const elapsed = open ? Math.max(0, Math.floor((serverNow - new Date(today.server_time).getTime()) / 1000)) : 0;
  const gross = today.totals.gross_seconds + elapsed;
  const breaks = today.totals.break_seconds + (open?.breaks.some((b) => b.ended_at === null) ? elapsed : 0);
  return (
    <>
      <DayHeading day={today.date} />
      <TotalsCards totals={{ gross_seconds: gross, break_seconds: breaks, net_seconds: Math.max(0, gross - breaks) }} />
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="text-base font-semibold">Completed sessions</h2>
          {completed.length === 0 ? (
            <p className="mt-3 text-sm text-dt-text-secondary">No completed sessions yet today.</p>
          ) : (
            <div className="mt-3 space-y-2">{completed.map((s) => <SessionRow key={s.id} session={s} zone={today.time_zone} format={format} href={`/attendance/${s.id}`} />)}</div>
          )}
        </Card>
        <Card className="p-5">
          <h2 className="text-base font-semibold">Activity</h2>
          {events.length === 0 ? (
            <p className="mt-3 text-sm text-dt-text-secondary">Nothing recorded yet today.</p>
          ) : (
            <ol className="mt-3 space-y-2 text-sm">
              {events.map((e, i) => (
                <li key={`${e.at}-${i}`} className="flex gap-3"><span className="w-14 shrink-0 font-mono text-dt-text-secondary">{time(e.at, today.time_zone, format)}</span><span>{e.label}</span></li>
              ))}
            </ol>
          )}
        </Card>
      </div>
    </>
  );
}

function TodayScreen() {
  const { scope } = useAtworkScope();
  const canRecord = hasPermission(scope, PERM.RECORD_OWN);
  const status = useLiveStatus();
  const today = useLiveToday();
  const policy = usePolicy();
  const online = useOnline();
  const client = useQueryClient();
  const action = useAttendanceAction(status.data?.state);
  const tick = useTick(Boolean(status.data));
  const offset = useServerOffset(status.data?.server_time, status.dataUpdatedAt);
  const serverNow = tick + offset;
  const modes = policy.data?.enabled_work_modes ?? ALL_WORK_MODES;
  const [chosen, setMode] = useState<WorkMode>("OFFICE");
  const mode = modes.includes(chosen) ? chosen : modes[0];

  // A new local day needs a fresh summary even if nothing else changed.
  const zone = status.data?.time_zone;
  const day = today.data?.date;
  const localDay = zone ? localDate(serverNow, zone) : null;
  useEffect(() => {
    if (localDay && day && localDay !== day) client.invalidateQueries({ queryKey: ["atwork", "today"] });
  }, [localDay, day, client]);

  if (status.isLoading || today.isLoading) return <LoadingState label="Loading your attendance…" />;
  if (!status.data) return <QueryError error={status.error} retry={() => status.refetch()} />;
  if (!today.data) return <QueryError error={today.error} retry={() => today.refetch()} />;

  const { state, session, server_time: serverTime } = status.data;
  const format = policy.data?.time_format ?? "24h";
  const totals = session ? liveTotals(session, serverTime, serverNow) : null;
  const openBreak = session?.breaks.find((b) => b.ended_at === null);
  const breakSeconds = openBreak ? Math.max(0, Math.floor((serverNow - new Date(openBreak.started_at).getTime()) / 1000)) : 0;
  const busy = action.pending !== null;
  const disabled = busy || !online;

  return (
    <>
      <PageHeader title="Today" description={`Times are shown in ${status.data.time_zone}.`} action={<StatusBadge status={state === "NOT_CHECKED_IN" ? "NOT_STARTED" : state === "WORKING" ? "ACTIVE" : "ON_HOLD"} label={state === "NOT_CHECKED_IN" ? "Not checked in" : state === "WORKING" ? "Working" : "On break"} />} />
      <OfflineBanner />
      {(status.isError || today.isError) && <Notice tone="info" action={<Button size="sm" variant="secondary" onClick={() => { status.refetch(); today.refetch(); }}>Refresh</Button>}>We could not refresh your attendance. The details below may be out of date.</Notice>}
      {action.notice && <Notice tone={action.notice.tone} action={action.retryable ? <Button size="sm" variant="secondary" disabled={disabled} onClick={action.retry}>Retry</Button> : undefined}>{action.notice.text}</Notice>}

      {session && policy.data && totals && totals.gross >= policy.data.missed_checkout_hours * 3600 && (
        <Notice tone="info" action={hasPermission(scope, PERM.REQUEST_OWN) ? <Link className="font-medium text-dt-burnt-orange underline underline-offset-2" href={`/requests/new?sessionId=${session.id}`}>Request correction</Link> : undefined}>
          This session has been open for over {policy.data.missed_checkout_hours} hours. If you forgot to check out, request a correction.
        </Notice>
      )}
      <Card className="mb-6 p-5 sm:p-6">
        {state === "NOT_CHECKED_IN" && (
          canRecord ? (
            <div>
              <fieldset>
                <legend className="text-sm font-medium">Where are you working today?</legend>
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  {modes.map((m) => (
                    <label key={m} className={`flex cursor-pointer items-center gap-2 rounded-xl border p-3 text-sm focus-within:ring-2 focus-within:ring-dt-orange ${mode === m ? "border-dt-orange bg-dt-surface-warm font-medium" : "border-dt-border"}`}>
                      <input type="radio" name="work-mode" className="accent-dt-orange" checked={mode === m} onChange={() => setMode(m)} />
                      {WORK_MODE_LABEL[m]}
                    </label>
                  ))}
                </div>
              </fieldset>
              <Button className="mt-4 w-full py-3 sm:w-auto sm:px-8" loading={action.pending === "CHECK_IN"} disabled={disabled} onClick={() => action.run({ kind: "CHECK_IN", workMode: mode })}><LogIn className="size-4" aria-hidden />Check In</Button>
            </div>
          ) : <p className="text-sm text-dt-text-secondary">You are not checked in. Your role can view attendance but cannot record it.</p>
        )}
        {session && totals && (
          <div>
            <div className="flex flex-wrap items-end gap-x-10 gap-y-4">
              {state === "ON_BREAK" ? <Timer label="Current break" seconds={breakSeconds} large /> : <Timer label="Net working time" seconds={totals.net} large />}
              <Timer label="Session elapsed" seconds={totals.gross} />
              {state === "ON_BREAK" ? <Timer label="Net working time" seconds={totals.net} /> : <Timer label="Break time" seconds={totals.breaks} />}
            </div>
            <p className="mt-4 text-sm text-dt-text-secondary">{WORK_MODE_LABEL[session.work_mode]} · Started {time(session.check_in_at, status.data.time_zone, format)}{openBreak ? ` · On break since ${time(openBreak.started_at, status.data.time_zone, format)}` : ""}</p>
            {canRecord && (
              <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                {state === "WORKING" ? (
                  <>
                    <Button variant="secondary" loading={action.pending === "BREAK_START"} disabled={disabled} onClick={() => action.run({ kind: "BREAK_START" })}><Coffee className="size-4" aria-hidden />Start Break</Button>
                    <Button loading={action.pending === "CHECK_OUT"} disabled={disabled} onClick={() => action.run({ kind: "CHECK_OUT" })}><LogOut className="size-4" aria-hidden />Check Out</Button>
                  </>
                ) : (
                  <>
                    <Button loading={action.pending === "BREAK_END"} disabled={disabled} onClick={() => action.run({ kind: "BREAK_END" })}><Play className="size-4" aria-hidden />End Break</Button>
                    <p className="self-center text-sm text-dt-text-secondary">End your break before checking out.</p>
                  </>
                )}
              </div>
            )}
            {!canRecord && <p className="mt-4 text-sm text-dt-text-secondary">Your role can view attendance but cannot record it.</p>}
            <Link href={`/attendance/${session.id}`} className="mt-4 inline-block text-sm font-medium text-dt-burnt-orange underline underline-offset-2">Session details</Link>
          </div>
        )}
      </Card>

      {today.data.session_count === 0 && state === "NOT_CHECKED_IN" ? <EmptyState title="No attendance recorded today" description="Your sessions will appear here after you check in." /> : <TodaySummary today={today.data} format={format} serverNow={serverNow} />}
    </>
  );
}

export default function TodayPage() {
  return <Page><RequirePermission permission={PERM.READ_OWN} title="Attendance access required"><TodayScreen /></RequirePermission></Page>;
}
