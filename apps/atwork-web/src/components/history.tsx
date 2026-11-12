"use client";

import { Button } from "@dijione/design-system";
import type { DayTotals, Session } from "@/lib/api";
import { localDate, type TimeFormat } from "@/lib/format";
import { DayHeading, SessionRow } from "./ui";

/** Sessions under each local day they touch, so overnight work appears on both. */
export function groupByDay(sessions: Session[], daily: DayTotals[], zone: string, serverNow: string) {
  return [...daily]
    .sort((a, b) => b.date.localeCompare(a.date))
    .map((d) => ({
      day: d,
      sessions: sessions.filter((s) => localDate(s.check_in_at, zone) <= d.date && d.date <= localDate(s.check_out_at ?? serverNow, zone)),
    }))
    .filter((g) => g.sessions.length > 0);
}

export function HistoryList({ sessions, daily, zone, format, hrefFor, total, onMore, loading }: {
  sessions: Session[]; daily: DayTotals[]; zone: string; format: TimeFormat; hrefFor: (s: Session) => string;
  total: number; onMore: () => void; loading: boolean;
}) {
  return (
    <div className="space-y-6">
      {groupByDay(sessions, daily, zone, new Date().toISOString()).map((g) => (
        <section key={g.day.date}>
          <DayHeading day={g.day.date} totals={g.day} />
          <div className="space-y-2">{g.sessions.map((s) => <SessionRow key={s.id} session={s} zone={zone} format={format} href={hrefFor(s)} />)}</div>
        </section>
      ))}
      {sessions.length < total && <div className="text-center"><Button variant="secondary" loading={loading} onClick={onMore}>Load more</Button></div>}
    </div>
  );
}
