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

/** Field labels used consistently across the module. */
export const ID_LABELS = {
  zk: "ZKBioTime ID",
  bhr: "BHR Employee ID",
  number: "EMP Number",
  name: "Team Member Name",
  mapping: "Mapping Status",
} as const;

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}
