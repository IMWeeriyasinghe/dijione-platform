/**
 * Formatting for the Recruitment (Lever) sync timestamp.
 *
 * The backend sends `last_successful_sync_at` as ISO-8601. PostgreSQL
 * returns it with an offset (`…+00:00`); a timezone-naive value (local
 * SQLite) is the backend's UTC clock, so it is read as UTC rather than as
 * the browser's local time.
 */
export function parseSyncInstant(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "13 Nov 2026, 4:30 PM" in the viewer's local zone (or `timeZone`). */
export function formatSyncAbsolute(d: Date, timeZone?: string): string {
  const date = new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone,
  }).format(d);
  const time = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone,
  }).format(d);
  return `${date}, ${time}`;
}

/** Full, unambiguous form for the tooltip / accessible label, e.g.
 * "13 November 2026 at 4:30:12 PM GMT+5:30 (Asia/Colombo)". */
export function formatSyncTooltip(d: Date, timeZone?: string): string {
  const zone = timeZone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  const full = new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
    timeZoneName: "short",
    timeZone: zone,
  }).format(d);
  return `Last successful Lever sync: ${full} (${zone})`;
}

export function relativeSyncTime(d: Date | null, now: number = Date.now()): string {
  if (!d) return "never";
  const mins = Math.round((now - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hr${hrs === 1 ? "" : "s"} ago`;
  const days = Math.round(hrs / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}
