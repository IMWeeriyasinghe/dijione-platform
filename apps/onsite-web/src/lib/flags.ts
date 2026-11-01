import type { ReviewFlag } from "./dashboard";

// Neutral review wording — flags mean "worth a look", never a judgement.
export const FLAG_LABEL: Record<ReviewFlag, string> = {
  SINGLE_PUNCH: "Single activity",
  POSSIBLE_DUPLICATE_TAP: "Possible duplicate tap",
  UNMATCHED_CODE: "Unmatched code",
  AMBIGUOUS_CODE: "Ambiguous code",
  INACTIVE_EMPLOYEE_ACTIVITY: "Inactive employee activity",
  BEFORE_HIRE_ACTIVITY: "Before-hire activity",
  TZ_INCONSISTENT: "Time zone inconsistent",
  HIGH_PUNCH_COUNT: "High activity count",
};

/** Local time "HH:MM" from an ISO string that already carries the site offset. */
export function localTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /T(\d{2}:\d{2})/.exec(iso);
  return m ? m[1] : iso;
}

export function formatSpan(minutes: number): string {
  if (!minutes) return "—";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h}h ${m.toString().padStart(2, "0")}m` : `${m}m`;
}

export function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
