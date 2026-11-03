import { addDays } from "./flags";

// Periods are always expressed as site-local ISO dates ("YYYY-MM-DD"). "Today"
// comes from onsite-api (`site.today`, computed in the site's own time zone,
// e.g. Asia/Colombo) — never from the browser clock or UTC.

export type PresetKey = "today" | "yesterday" | "7d" | "30d" | "custom";
export type Period = { from: string; to: string };

export const PRESETS: { key: Exclude<PresetKey, "custom">; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
];

export const MAX_RANGE_DAYS = 92; // onsite-api's bound for every range query

export function presetPeriod(key: Exclude<PresetKey, "custom">, today: string): Period {
  switch (key) {
    case "today":
      return { from: today, to: today };
    case "yesterday": {
      const y = addDays(today, -1);
      return { from: y, to: y };
    }
    case "7d":
      return { from: addDays(today, -6), to: today };
    case "30d":
      return { from: addDays(today, -29), to: today };
  }
}

/** Which preset (if any) a period corresponds to, relative to `today`. */
export function presetOf(p: Period, today: string): PresetKey {
  for (const { key } of PRESETS) {
    const q = presetPeriod(key, today);
    if (q.from === p.from && q.to === p.to) return key;
  }
  return "custom";
}

export function dayCount(p: Period): number {
  return Math.round((Date.parse(`${p.to}T00:00:00Z`) - Date.parse(`${p.from}T00:00:00Z`)) / 86_400_000) + 1;
}

/** The equivalent period immediately before `p` (same length). */
export function previousPeriod(p: Period): Period {
  const n = dayCount(p);
  return { from: addDays(p.from, -n), to: addDays(p.from, -1) };
}

export function isSingleDay(p: Period): boolean {
  return p.from === p.to;
}

/** Clamp a user-entered range: ordered, and at most MAX_RANGE_DAYS long. */
export function normalizePeriod(p: Period): Period {
  let { from, to } = p;
  if (from > to) [from, to] = [to, from];
  if (dayCount({ from, to }) > MAX_RANGE_DAYS) from = addDays(to, -(MAX_RANGE_DAYS - 1));
  return { from, to };
}

const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Mon 3 Nov" (or "Mon 3 Nov 2025" when `withYear`) — locale-stable and
 *  timezone-free: the ISO date is already site-local. */
export function fmtDay(iso: string, withYear = false): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  const wd = WEEKDAY[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  return `${wd} ${d} ${MONTH[m - 1]}${withYear ? ` ${y}` : ""}`;
}

/** "3 Nov" */
export function fmtShortDay(iso: string): string {
  const [, m, d] = iso.split("-").map(Number);
  return m && d ? `${d} ${MONTH[m - 1]}` : iso;
}

export function fmtPeriod(p: Period, today?: string): string {
  if (isSingleDay(p)) {
    const label = fmtDay(p.from, p.from.slice(0, 4) !== (today ?? p.from).slice(0, 4));
    if (today && p.from === today) return `Today · ${label}`;
    if (today && p.from === addDays(today, -1)) return `Yesterday · ${label}`;
    return label;
  }
  return `${fmtShortDay(p.from)} – ${fmtShortDay(p.to)} ${p.to.slice(0, 4)} (${dayCount(p)} days)`;
}

/** Every ISO date from `from` to `to` inclusive. */
export function eachDay(p: Period): string[] {
  const out: string[] = [];
  for (let d = p.from; d <= p.to && out.length <= MAX_RANGE_DAYS; d = addDays(d, 1)) out.push(d);
  return out;
}

export const fmtNum = (n: number | null | undefined): string => (n == null ? "—" : n.toLocaleString("en-GB"));
