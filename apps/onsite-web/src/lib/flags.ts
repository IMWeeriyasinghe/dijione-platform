import type { ReviewFlag } from "./dashboard";

// Neutral review wording — flags mean "worth a look", never a judgement.
export const FLAG_LABEL: Record<ReviewFlag, string> = {
  SINGLE_PUNCH: "Single activity",
  POSSIBLE_DUPLICATE_TAP: "Possible duplicate tap",
  UNMATCHED_CODE: "Unmapped ZKBioTime ID",
  AMBIGUOUS_CODE: "Mapping conflict",
  INACTIVE_EMPLOYEE_ACTIVITY: "Inactive team member activity",
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

/** What each flag means — the same neutral wording onsite-api uses for the
 *  Exceptions "reasons". A flag is a prompt to look, never a policy breach. */
export const FLAG_HELP: Record<ReviewFlag, string> = {
  SINGLE_PUNCH: "Only one activity was recorded on this completed day.",
  POSSIBLE_DUPLICATE_TAP: "Two activities were recorded within 60 seconds of each other.",
  UNMATCHED_CODE: "The ZKBioTime ID has no verified BambooHR mapping for this day.",
  AMBIGUOUS_CODE: "More than one verified mapping covers this ZKBioTime ID on this day.",
  INACTIVE_EMPLOYEE_ACTIVITY: "Activity is recorded for a team member who is inactive or past their termination date.",
  BEFORE_HIRE_ACTIVITY: "Activity is recorded before the team member's hire date.",
  TZ_INCONSISTENT: "The source local time does not match the site's configured time zone.",
  HIGH_PUNCH_COUNT: "An unusually high number of activities was recorded on this day.",
};

/** Data-quality flags concern identity/source data rather than the day's
 *  activity pattern; shown in a cooler tone. */
export const DATA_QUALITY_FLAGS = new Set<ReviewFlag>(["UNMATCHED_CODE", "AMBIGUOUS_CODE", "TZ_INCONSISTENT"]);
