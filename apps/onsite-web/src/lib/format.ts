import type { FeedState, IdentityClass, MappingStatus } from "./types";

// Neutral wording only (docs/onsite/requirements.md "Business rules"): no
// Present/Absent/Late/Early/working hours until an attendance policy exists.
export const FEED_LABEL: Record<FeedState, string> = {
  FRESH: "Feed current",
  DELAYED: "Feed delayed",
  STALE: "Feed stale",
  SOURCE_UNAVAILABLE: "Source unavailable",
  NOT_SYNCED: "Not yet synced",
};

export const FEED_TONE: Record<FeedState, "success" | "warning" | "danger" | "neutral"> = {
  FRESH: "success",
  DELAYED: "warning",
  STALE: "danger",
  SOURCE_UNAVAILABLE: "danger",
  NOT_SYNCED: "neutral",
};

export const IDENTITY_LABEL: Record<IdentityClass, string> = {
  MATCHED_ACTIVE: "Verified · active",
  MATCHED_INACTIVE: "Verified · inactive",
  MATCHED_BEFORE_HIRE: "Verified · before hire date",
  AMBIGUOUS: "Conflicting mapping",
  UNMATCHED: "Unmapped ZKBioTime ID",
};

export const MAPPING_LABEL: Record<MappingStatus, string> = {
  MAPPED: "Verified",
  MAPPED_DIRECTORY_MISSING: "Verified · not in directory",
  UNMAPPED: "Unmapped",
  MAPPING_CONFLICT: "Mapping conflict",
  DIRECTORY_UNAVAILABLE: "Verified · directory unavailable",
};

/** Field labels used consistently across the module.
 *  BHR ID = BambooHR's internal record id; EMP Number = the organisation's employee number. */
export const ID_LABELS = {
  zk: "ZKBioTime ID",
  bhr: "BHR ID",
  number: "EMP Number",
  name: "Team Member Name",
  mapping: "Mapping Status",
} as const;

/* ------------------------------------------------- identity status (shared) */

export type StatusTone = "success" | "warning" | "danger";

/** One identity-status vocabulary and colour set for Overview, Activity and
 *  Identity Management. Verified = green, unmapped / needs review = amber,
 *  mapping conflict = red (never attributed). Punch sequence (first / last)
 *  is a separate dimension and never uses these colours. */
export const MAPPING_STATE: Record<"VERIFIED" | "UNMAPPED" | "CONFLICT", {
  label: string; short: string; tone: StatusTone; bar: string; text: string; help: string;
}> = {
  // Chart bars use the onsite-local data palette (globals.css: teal/blue · amber ·
  // burgundy gradients plus a non-colour pattern); badges keep semantic tones.
  VERIFIED: {
    label: "Verified", short: "Verified", tone: "success", bar: "onsite-bar-verified", text: "text-dt-success",
    help: "A verified ZKBioTime ID mapping covers this day, so the event is attributed to that team member.",
  },
  UNMAPPED: {
    label: "Unmapped — needs review", short: "Unmapped", tone: "warning", bar: "onsite-bar-unmapped", text: "text-dt-warning",
    help: "No verified mapping covers this ZKBioTime ID on this day. The event is stored and shown by ID only — never as a team member.",
  },
  CONFLICT: {
    label: "Mapping conflict", short: "Conflict", tone: "danger", bar: "onsite-bar-conflict", text: "text-dt-danger",
    help: "More than one mapping covers this ZKBioTime ID on this day. It is never attributed until an administrator resolves it.",
  },
};

export const MAPPING_FILTER_OPTIONS = [
  { value: "all", label: "All activity" },
  { value: "verified", label: "Verified" },
  { value: "unverified", label: "Unmapped / needs review" },
  { value: "conflict", label: "Mapping conflict" },
] as const;

export const SEQUENCE_LABEL: Record<"FIRST" | "LAST" | "INTERMEDIATE" | "SINGLE", string> = {
  FIRST: "First recorded fingerprint",
  LAST: "Last recorded fingerprint",
  INTERMEDIATE: "Intermediate",
  SINGLE: "Single Recorded Fingerprint",
};

/** Entry-side reader + anonymous push-to-exit button: no exit is ever recorded. */
export const FINGERPRINT_DISCLAIMER =
  "Recorded at the entry-side fingerprint reader — not a confirmed exit, presence or hours worked.";
export const RECORDED_SPAN_HELP =
  "Time between the first and last recorded fingerprint. A measured interval between observations — not a confirmed exit, presence or hours worked. Unavailable for a Single Recorded Fingerprint.";

/** Recorded Span text: "—" when unavailable (a single fingerprint), never 0h. */
export function formatRecordedSpan(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}
