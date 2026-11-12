"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, WifiOff } from "lucide-react";
import { Button, Card, EmptyState, ErrorState, FormField, Input, MetricCard, StatusBadge } from "@dijione/design-system";
import { Clock3, Coffee, Timer } from "lucide-react";
import { errorMessage, type Correction, type CorrectionValues, type Session, type Totals } from "@/lib/api";
import { dateTime, duration, longDate, rangeError, shortDuration, time, WORK_MODE_LABEL, type TimeFormat } from "@/lib/format";
import { hasPermission, useAtworkScope } from "@/lib/atwork-scope";
import { useOnline } from "@/lib/hooks";

export function Page({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto w-full max-w-6xl">{children}</div>;
}

export function RequirePermission({ permission, title, children }: { permission: string | string[]; title: string; children: React.ReactNode }) {
  const { scope } = useAtworkScope();
  const needed = Array.isArray(permission) ? permission : [permission];
  if (!needed.every((p) => hasPermission(scope, p))) {
    return <EmptyState title={title} description="Your DijiAtWork role does not include this area." />;
  }
  return <>{children}</>;
}

export function Notice({ tone, children, action }: { tone: "success" | "error" | "info"; children: React.ReactNode; action?: React.ReactNode }) {
  const color = { success: "border-dt-success/30 text-dt-success", error: "border-dt-danger/30 text-dt-danger", info: "border-dt-warning/30 text-dt-warning" }[tone];
  const Icon = tone === "success" ? CheckCircle2 : AlertTriangle;
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`mb-4 flex flex-wrap items-center gap-2 rounded-xl border bg-dt-surface px-4 py-3 text-sm ${color}`}>
      <Icon className="size-4 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1 text-dt-text-primary">{children}</span>
      {action}
    </div>
  );
}

export function OfflineBanner() {
  const online = useOnline();
  if (online) return null;
  return (
    <div role="status" className="mb-4 flex items-center gap-2 rounded-xl border border-dt-warning/30 bg-dt-surface px-4 py-3 text-sm text-dt-text-primary">
      <WifiOff className="size-4 shrink-0 text-dt-warning" aria-hidden />
      You are offline. Times shown may be out of date, and actions cannot be recorded until you reconnect.
    </div>
  );
}

export function QueryError({ error, retry }: { error: unknown; retry: () => void }) {
  return <ErrorState message={errorMessage(error)} onRetry={retry} />;
}

export const UNVERIFIED_HELP = "Not counted until the session is checked out and confirmed through a correction.";

export function TotalsCards({ totals }: { totals: Totals }) {
  const unverified = totals.provisional_seconds ?? 0;
  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCard label="Gross time" value={shortDuration(totals.gross_seconds)} icon={Clock3} />
        <MetricCard label="Break time" value={shortDuration(totals.break_seconds)} icon={Coffee} />
        <MetricCard label="Net working time" value={shortDuration(totals.net_seconds)} icon={Timer} tone="brand" />
      </div>
      {unverified > 0 && (
        <p className="mt-2 text-sm text-dt-warning">Unverified time, not included above: {shortDuration(unverified)}. {UNVERIFIED_HELP}</p>
      )}
    </>
  );
}

export function SessionBadge({ session }: { session: Session }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      <StatusBadge status={session.status === "OPEN" ? "ACTIVE" : "COMPLETED"} label={session.status === "OPEN" ? "Active" : "Completed"} />
      {session.correction_count > 0 && <StatusBadge status="CONFIRMED" label="Corrected" />}
      {session.unverified && <StatusBadge status="PENDING" label="Unverified" />}
    </span>
  );
}

export function SessionRow({ session, zone, format, href }: { session: Session; zone: string; format: TimeFormat; href: string }) {
  return (
    <Link href={href} className="block rounded-xl border border-dt-border p-4 hover:border-dt-orange/40 focus-visible:outline-2 focus-visible:outline-dt-orange">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-dt-text-primary">
          {dateTime(session.check_in_at, zone, format)} → {session.check_out_at ? dateTime(session.check_out_at, zone, format) : "In progress"}
        </p>
        <SessionBadge session={session} />
      </div>
      <p className="mt-1 text-sm text-dt-text-secondary">
        {WORK_MODE_LABEL[session.work_mode]} · Gross {shortDuration(session.totals.gross_seconds)} · Break {shortDuration(session.totals.break_seconds)} · Net{" "}
        {shortDuration(session.totals.net_seconds)}
      </p>
    </Link>
  );
}

export function SessionDetails({ session, zone, format }: { session: Session; zone: string; format: TimeFormat }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-5">
        <h2 className="text-base font-semibold">Session</h2>
        <dl className="mt-3 space-y-2 text-sm">
          {[
            ["Work mode", WORK_MODE_LABEL[session.work_mode]],
            ["Check-in", dateTime(session.check_in_at, zone, format)],
            ["Check-out", session.check_out_at ? dateTime(session.check_out_at, zone, format) : "In progress"],
            ["Gross", duration(session.totals.gross_seconds)],
            ["Breaks", duration(session.totals.break_seconds)],
            ["Net", duration(session.totals.net_seconds)],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between gap-4">
              <dt className="text-dt-text-secondary">{k}</dt>
              <dd className="text-right font-medium">{v}</dd>
            </div>
          ))}
        </dl>
      </Card>
      <Card className="p-5">
        <h2 className="text-base font-semibold">Breaks</h2>
        {session.breaks.length === 0 ? (
          <p className="mt-3 text-sm text-dt-text-secondary">No breaks recorded.</p>
        ) : (
          <ul className="mt-3 space-y-2 text-sm">
            {session.breaks.map((b) => (
              <li key={b.id} className="flex justify-between gap-4">
                <span>{time(b.started_at, zone, format)} – {b.ended_at ? time(b.ended_at, zone, format) : "In progress"}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

export function DateRange({ from, to, onApply }: { from: string; to: string; onApply: (from: string, to: string) => void }) {
  const [a, setA] = useState(from);
  const [b, setB] = useState(to);
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const problem = rangeError(a, b);
        setError(problem);
        if (!problem) onApply(a, b);
      }}
    >
      <FormField label="From" htmlFor="range-from"><Input id="range-from" type="date" value={a} onChange={(e) => setA(e.target.value)} /></FormField>
      <FormField label="To" htmlFor="range-to"><Input id="range-to" type="date" value={b} onChange={(e) => setB(e.target.value)} /></FormField>
      <Button type="submit" variant="secondary">Apply</Button>
      {error && <p role="alert" className="w-full text-sm text-dt-danger">{error}</p>}
    </form>
  );
}

export function Pager({ total, limit, offset, onChange }: { total: number; limit: number; offset: number; onChange: (offset: number) => void }) {
  if (total <= limit) return null;
  return (
    <nav aria-label="Pagination" className="mt-4 flex items-center justify-between gap-3 text-sm text-dt-text-secondary">
      <span>{offset + 1}–{Math.min(offset + limit, total)} of {total}</span>
      <span className="flex gap-2">
        <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</Button>
        <Button variant="secondary" size="sm" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</Button>
      </span>
    </nav>
  );
}

function values(v: CorrectionValues | null, zone: string, format: TimeFormat) {
  if (!v) return { mode: "—", in: "No session on record", out: "—", breaks: "—" };
  return {
    mode: WORK_MODE_LABEL[v.work_mode],
    in: dateTime(v.check_in_at, zone, format),
    out: v.check_out_at ? dateTime(v.check_out_at, zone, format) : "Not checked out",
    breaks: v.breaks.length ? v.breaks.map((b) => `${time(b.started_at, zone, format)}–${b.ended_at ? time(b.ended_at, zone, format) : "open"}`).join(", ") : "None",
  };
}

export function CorrectionComparison({ item, zone, format }: { item: Correction; zone: string; format: TimeFormat }) {
  const a = values(item.original, zone, format);
  const b = values(item.proposed, zone, format);
  const rows: [string, string, string][] = [["Work mode", a.mode, b.mode], ["Check-in", a.in, b.in], ["Check-out", a.out, b.out], ["Breaks", a.breaks, b.breaks]];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[420px] text-sm">
        <caption className="sr-only">Original and proposed values</caption>
        <thead><tr className="text-left text-xs text-dt-text-secondary"><th scope="col" className="py-2 pr-3 font-medium">Field</th><th scope="col" className="py-2 pr-3 font-medium">Original</th><th scope="col" className="py-2 font-medium">Proposed</th></tr></thead>
        <tbody>
          {rows.map(([label, x, y]) => (
            <tr key={label} className="border-t border-dt-border">
              <th scope="row" className="py-2 pr-3 text-left font-normal text-dt-text-secondary">{label}</th>
              <td className="py-2 pr-3">{x}</td>
              <td className={`py-2 ${x !== y ? "font-semibold text-dt-burnt-orange" : ""}`}>{y}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const CORRECTION_TITLE = { AMEND: "Session correction", CREATE_MISSING: "Missing session" } as const;

export function DayHeading({ day, totals }: { day: string; totals?: Totals }) {
  const unverified = totals?.provisional_seconds ?? 0;
  return (
    <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
      <h2 className="text-base font-semibold">{longDate(day)}</h2>
      {totals && (
        <p className="text-sm text-dt-text-secondary">
          Gross {shortDuration(totals.gross_seconds)} · Break {shortDuration(totals.break_seconds)} · Net {shortDuration(totals.net_seconds)}
          {unverified > 0 && <span className="text-dt-warning"> · Unverified {shortDuration(unverified)}</span>}
        </p>
      )}
    </div>
  );
}
