import type { WorkMode } from "./api";

export const WORK_MODE_LABEL: Record<WorkMode, string> = { OFFICE: "Office", REMOTE: "Remote", CLIENT_SITE: "Client Site" };
export const ALL_WORK_MODES: WorkMode[] = ["OFFICE", "REMOTE", "CLIENT_SITE"];
export type TimeFormat = "24h" | "12h";

export function duration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

export function shortDuration(totalSeconds: number): string {
  const minutes = Math.floor(Math.max(0, totalSeconds) / 60);
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

export function time(iso: string, zone: string, format: TimeFormat = "24h"): string {
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: format === "12h", timeZone: zone }).format(new Date(iso));
}

export function dateTime(iso: string, zone: string, format: TimeFormat = "24h"): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: format === "12h", timeZone: zone,
  }).format(new Date(iso));
}

/** The calendar date (YYYY-MM-DD) of an instant in a zone. */
export function localDate(iso: string | number, zone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(iso));
}

export function longDate(day: string): string {
  return new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(`${day}T00:00:00Z`),
  );
}

export function addDays(day: string, delta: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

function parts(ms: number, zone: string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const p of new Intl.DateTimeFormat("en-US", {
    timeZone: zone, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", second: "numeric",
  }).formatToParts(new Date(ms))) {
    if (p.type !== "literal") out[p.type] = Number(p.value);
  }
  return out;
}

function zoneOffset(ms: number, zone: string): number {
  const p = parts(ms, zone);
  return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) - Math.floor(ms / 1000) * 1000;
}

/** A datetime-local value, read in the business time zone, as a UTC ISO string. */
export function localInputToUtc(value: string, zone: string): string {
  const [d, t] = value.split("T");
  const [y, m, day] = d.split("-").map(Number);
  const [h, min, s = 0] = t.split(":").map(Number);
  const wall = Date.UTC(y, m - 1, day, h, min, s);
  let utc = wall - zoneOffset(wall, zone);
  utc = wall - zoneOffset(utc, zone);
  return new Date(utc).toISOString().replace(".000Z", "Z");
}

export function utcToLocalInput(iso: string, zone: string): string {
  const p = parts(new Date(iso).getTime(), zone);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}:${pad(p.second)}`;
}

export function rangeError(from: string, to: string): string | null {
  if (!from || !to) return "Choose both a start and an end date.";
  if (from > to) return "The start date must not be after the end date.";
  if ((new Date(to).getTime() - new Date(from).getTime()) / 86_400_000 >= 366) return "The date range must not exceed 366 days.";
  return null;
}
