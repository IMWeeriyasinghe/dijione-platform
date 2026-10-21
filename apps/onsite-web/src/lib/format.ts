import type { FeedState, IdentityClass } from "./types";

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
  MATCHED_ACTIVE: "Matched (active)",
  MATCHED_INACTIVE: "Matched (inactive)",
  MATCHED_BEFORE_HIRE: "Matched (before hire date)",
  AMBIGUOUS: "Ambiguous Employee Number",
  UNMATCHED: "No matching Employee Number",
};

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}
