import { ApiError } from "@dijione/auth-client";
import type { DeclarationSource, ExceptionType, JustificationReason, Outcome, ReassessReason, ReviewStatus, ReviewSummary } from "./dashboard";

// Neutral, informative wording (owner corrections 2026-11-19): a review case is an
// administrative record; a Single Recorded Fingerprint is an observation, never a violation;
// "resolved" never means a verified duration; the final fingerprint is never an exit.

export const STATUS_LABEL: Record<ReviewStatus, string> = {
  OPEN: "Under review",
  SUBMITTED: "Justification submitted",
  RESOLVED: "Resolved (duration not verified)",
  REOPENED: "Reopened",
};
export const STATUS_TONE: Record<ReviewStatus, "neutral" | "warning" | "success"> = {
  OPEN: "warning", SUBMITTED: "neutral", RESOLVED: "success", REOPENED: "warning",
};
export const TYPE_LABEL: Record<ExceptionType, string> = {
  SINGLE_RECORDED_FINGERPRINT: "Single Recorded Fingerprint",
  DEPARTURE_TIME_QUERY: "Departure time query",
  DISPUTED_SPAN: "Disputed Recorded Span",
  DEVICE_ISSUE: "Device issue",
  IDENTITY_ISSUE: "Identity issue",
  OTHER: "Other",
};
export const REASON_LABEL: Record<JustificationReason, string> = {
  FORGOT_TO_RECORD: "Fingerprint not recorded",
  DEVICE_FAULT: "Device fault",
  ASSIGNED_OFF_SITE: "Assigned off-site",
  APPROVED_LEAVE_OR_DUTY: "Approved leave or duty",
  OTHER: "Other",
};
export const SOURCE_LABEL: Record<DeclarationSource, string> = {
  TEAM_MEMBER_STATEMENT: "Team member statement",
  MANAGER_CONFIRMATION: "Manager confirmation",
  SECURITY_OR_VISITOR_LOG: "Security or visitor log",
  OTHER: "Other",
};
export const OUTCOME_LABEL: Record<Outcome, string> = {
  JUSTIFIED: "Justified",
  NO_FURTHER_ACTION: "No further action",
  NOT_JUSTIFIED: "Not justified",
};
export const REASSESS_LABEL: Record<ReassessReason, string> = {
  FINGERPRINTS_CHANGED: "Recorded fingerprints changed",
  IDENTITY_CHANGED: "Identity mapping changed",
  ESTIMATE_BASIS_INVALID: "A fingerprint is now later than the declared departure",
};
export const REVIEW_STATUS_FILTERS = [
  { value: "", label: "Any review status" },
  { value: "not_reviewed", label: "Not reviewed" },
  { value: "OPEN", label: "Under review" },
  { value: "SUBMITTED", label: "Justification submitted" },
  { value: "RESOLVED", label: "Resolved" },
  { value: "REOPENED", label: "Reopened" },
  { value: "NEEDS_REASSESSMENT", label: "Needs reassessment" },
] as const;

export const MIN_TEXT = 10;

/** One readable message from any review API error (409 conflict, 422 validation, 403, 503). */
export function reviewError(e: unknown): string {
  if (e instanceof ApiError) {
    const detail = (e.body as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as { msg?: string; loc?: string[] };
      return `${first.loc?.at(-1) ?? "Field"}: ${first.msg ?? "invalid value"}`;
    }
    if (detail && typeof detail === "object" && "error" in detail) return String((detail as { error: string }).error);
    if (e.status === 403) return "You do not have permission to change attendance reviews.";
    return e.message;
  }
  return e instanceof Error ? e.message : "The change was not saved.";
}

/** "Needs reassessment" overlay for any status. */
export function needsReassessment(r: ReviewSummary | null | undefined): boolean {
  return Boolean(r?.stale);
}
