import { authorizedFetch, qs, request } from "@dijione/auth-client";
import { ONSITE_API } from "./api";
import type { FeedState, IdentityClass, MappingStatus } from "./types";

// Dashboard V1 DTOs — mirror onsite-api's /api/onsite dashboard routes.
// Neutral attendance facts only; PunchState is carried raw, never interpreted.

export const REVIEW_FLAGS = [
  "SINGLE_PUNCH",
  "POSSIBLE_DUPLICATE_TAP",
  "UNMATCHED_CODE",
  "AMBIGUOUS_CODE",
  "INACTIVE_EMPLOYEE_ACTIVITY",
  "BEFORE_HIRE_ACTIVITY",
  "TZ_INCONSISTENT",
  "HIGH_PUNCH_COUNT",
] as const;
export type ReviewFlag = (typeof REVIEW_FLAGS)[number];

/** Flags that can appear on viewer records. Unverified IDs are excluded from
 *  attendance entirely, so UNMATCHED_CODE / AMBIGUOUS_CODE never occur there
 *  (they remain in the API vocabulary for compatibility only). */
export const VIEWER_REVIEW_FLAGS = REVIEW_FLAGS.filter((f) => f !== "UNMATCHED_CODE" && f !== "AMBIGUOUS_CODE");

export type OnsiteSiteInfo = {
  site_id: string;
  name: string;
  time_zone: string | null;
  today: string;
  first_activity_date: string | null;
  last_activity_date: string | null;
  terminals: string[];
  departments?: string[];
};

export type Overview = {
  site_id: string;
  date: string;
  date_from?: string;
  date_to?: string;
  time_zone: string | null;
  directory_available: boolean;
  kpis: {
    employees_with_activity: number;
    total_events: number;
    /** Days in the period with any recorded activity. */
    activity_days?: number;
    employees_needing_review: number;
    single_punch_employees: number;
    /** Legacy key; always 0 now (unmapped IDs are excluded from attendance). */
    unmatched_codes: number;
    feed_state: FeedState | null;
    identified_employees?: number;
    identified_punches?: number;
    /** All recorded events in the period, by mapping state (= the charts and Activity "All"). */
    recorded_events?: number;
    verified_events?: number;
    unmapped_events?: number;
    conflict_events?: number;
  };
  /** Ingestion & identity coverage — only for Site Health / Identity readers. */
  operational?: { active_codes: number; total_punches: number; unmapped_codes: number; unmapped_punches: number };
  review_breakdown: Record<ReviewFlag, number>;
  /** Earliest / Latest Recorded Fingerprint (single site-local day only; null for a range). */
  extremes?: Extremes | null;
  last_successful_sync_at: string | null;
  latest_received_utc: string | null;
  agent_heartbeat_utc: string | null;
};

/** Mapping state of an event for its OWN site-local day. */
export type MappingState = "VERIFIED" | "UNMAPPED" | "CONFLICT";
/** Activity / chart filter: unverified = unmapped + conflict ("needs review"). */
export type MappingFilter = "all" | "verified" | "unverified" | "unmapped" | "conflict";
export type StateSplit = { verified_events: number; unmapped_events: number; conflict_events: number };
type BySeqState = { verified: number; unmapped: number; conflict: number };

/** ``events`` = ALL recorded events in the bucket (= verified + unmapped + conflict). */
export type HourBucket = StateSplit & {
  hour: number; events: number; employees: number;
  /** Identities whose first / last recorded punch of the whole day fell in this hour (single = only one punch). */
  first?: BySeqState; last?: BySeqState; single?: BySeqState;
};
export type TrendDay = StateSplit & { date: string; events: number; employees: number };

export type PunchSequence = "FIRST" | "LAST" | "INTERMEDIATE" | "SINGLE";

export type ActivitySummary = { recorded: number; verified: number; unverified: number; unmapped: number; conflict: number };

export type EmployeeRef = {
  /** A ZKBioTime ID of this verified team member (legacy row key). */
  emp_code: string;
  /** BHR ID — the verified identity key. */
  bamboohr_id?: string | null;
  /** EMP Number (HR reference only, never a matching key). */
  employee_number?: string | null;
  /** Every ZKBioTime ID verified to this team member for the row. */
  zk_emp_codes?: string[];
  mapping_status?: MappingStatus | null;
  employee_name: string | null;
  department: string | null;
  employment_status?: string | null;
  identity_class: IdentityClass | null;
  /** A profile photo may be requested (exact single directory match). */
  has_photo?: boolean;
};

export type ActivityEvent = EmployeeRef & {
  local_time: string;
  local_date: string;
  terminal: string | null;
  area: string | null;
  punch_state_raw: string | null;
  tz_consistent: boolean | null;
  event_id?: string;
  source_epoch?: number;
  verify_type?: number | null;
  /** Review flags of this event's team-member day. */
  review_flags?: ReviewFlag[];
  mapping_state?: MappingState;
  /** Position in the identity's complete site-local day (recorded order — not check-in/out). */
  punch_sequence?: PunchSequence;
  punch_position?: number;
  punches_in_day?: number;
  /** Whole identity-day bounds (recorded fingerprints — never entry/exit). */
  day_first_local?: string | null;
  day_last_local?: string | null;
  day_span_minutes?: number | null;
};

export type DayActivity = {
  local_date: string;
  emp_code: string;
  bamboohr_id?: string | null;
  employee_number?: string | null;
  zk_emp_codes?: string[];
  mapping_status?: MappingStatus | null;
  employment_status?: string | null;
  employee_name?: string | null;
  department?: string | null;
  has_photo?: boolean;
  first_activity_local: string | null;
  latest_activity_local: string | null;
  punch_count: number;
  /** Legacy (0 for a single fingerprint). Display ``recorded_span_minutes``. */
  span_minutes: number;
  /** Recorded Span: last − first recorded fingerprint; null = Single Recorded Fingerprint. */
  recorded_span_minutes?: number | null;
  terminal_names: string[];
  identity_class: IdentityClass | null;
  flags: ReviewFlag[];
  identity_key?: string;
  review?: ReviewSummary | null;
  earlier_code_cases?: ReviewSummary[];
};

/* ------------------------------------------------- v0.9 attendance reviews */

export const EXCEPTION_TYPES = ["SINGLE_RECORDED_FINGERPRINT", "DEPARTURE_TIME_QUERY", "DISPUTED_SPAN", "DEVICE_ISSUE", "IDENTITY_ISSUE", "OTHER"] as const;
export type ExceptionType = (typeof EXCEPTION_TYPES)[number];
export type ReviewStatus = "OPEN" | "SUBMITTED" | "RESOLVED" | "REOPENED";
export const JUSTIFICATION_REASONS = ["FORGOT_TO_RECORD", "DEVICE_FAULT", "ASSIGNED_OFF_SITE", "APPROVED_LEAVE_OR_DUTY", "OTHER"] as const;
export type JustificationReason = (typeof JUSTIFICATION_REASONS)[number];
export const DECLARATION_SOURCES = ["TEAM_MEMBER_STATEMENT", "MANAGER_CONFIRMATION", "SECURITY_OR_VISITOR_LOG", "OTHER"] as const;
export type DeclarationSource = (typeof DECLARATION_SOURCES)[number];
export const OUTCOMES = ["JUSTIFIED", "NO_FURTHER_ACTION", "NOT_JUSTIFIED"] as const;
export type Outcome = (typeof OUTCOMES)[number];
export type ReassessReason = "FINGERPRINTS_CHANGED" | "IDENTITY_CHANGED" | "ESTIMATE_BASIS_INVALID";

export type ReviewSummary = {
  id: number; status: ReviewStatus; exception_type: ExceptionType; justification_reason: JustificationReason | null;
  outcome: Outcome | null; estimated_minutes: number | null; declared_departure_local: string | null;
  reviewer: string | null; reviewed_at: string; version: number; duration_verified: false;
  stale: boolean; reassess_reasons: ReassessReason[]; identity_changed: boolean;
};

export type DayFacts = {
  punch_count: number; first_utc: string | null; last_utc: string | null; first_local: string | null; last_local: string | null;
  recorded_span_minutes: number | null; events_hash: string;
  mapping: { state: string; zk_emp_codes: string[]; mapping_ids: number[] };
};
export type DayPunch = { position: number; of: number; local_time: string; zk_emp_code: string; terminal: string | null; sequence: PunchSequence };

export type ReviewCase = {
  id: number; site_id: string; local_date: string; identity_kind: "PERSON" | "CODE"; identity_key: string;
  bamboohr_id: string | null; zk_emp_code: string | null;
  identity_snapshot: { kind: string; mapping_state: string; zk_emp_codes: string[]; mapping_ids: number[] };
  exception_type: ExceptionType; status: ReviewStatus; version: number; allowed_actions: ("submit" | "resolve" | "reopen")[];
  justification_reason: JustificationReason | null; explanation: string | null; declared_departure_local: string | null;
  declaration_source: DeclarationSource | null; evidence_reference: string | null; estimated_minutes: number | null;
  estimate_basis: string | null; outcome: Outcome | null; decision_note: string | null; duration_verified: false;
  facts_snapshot: DayFacts; opened_by_name: string | null; opened_at: string | null; submitted_by_name: string | null;
  submitted_at: string | null; resolved_by_name: string | null; resolved_at: string | null; reopened_by_name: string | null;
  reopened_at: string | null; reopen_reason: string | null;
  stale?: boolean; reassess_reasons?: ReassessReason[]; identity_changed?: boolean;
};
export type ReviewHistory = { action: string; from_status: ReviewStatus | null; to_status: ReviewStatus; version: number; actor_name: string | null; at: string; note: string | null };
export type ReviewDetail = {
  case: ReviewCase | null; history: ReviewHistory[]; current_facts: DayFacts; punches: DayPunch[]; can_manage: boolean; created?: boolean;
};

export const getReviewDay = (p: { site_id: string; date: string; bamboohr_id?: string; zk_emp_code?: string }) =>
  request<ReviewDetail>(`${ONSITE_API}/reviews/day${qs(p)}`);
const post = <T,>(path: string, body: unknown) =>
  request<T>(`${ONSITE_API}${path}`, { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
export const openReview = (body: { site_id: string; local_date: string; bamboohr_id?: string; zk_emp_code?: string; exception_type: ExceptionType; note?: string }) =>
  post<ReviewDetail>("/reviews", body);
export const submitReview = (id: number, body: {
  expected_version: number; justification_reason: JustificationReason; explanation: string;
  declared_departure_local?: string | null; declaration_source?: DeclarationSource | null; evidence_reference?: string | null;
}) => post<ReviewDetail>(`/reviews/${id}/submit`, body);
export const resolveReview = (id: number, body: { expected_version: number; outcome: Outcome; decision_note: string }) =>
  post<ReviewDetail>(`/reviews/${id}/resolve`, body);
export const reopenReview = (id: number, body: { expected_version: number; reason: string }) =>
  post<ReviewDetail>(`/reviews/${id}/reopen`, body);

/* ------------------------------------------------- v0.9 daily fingerprint activity */

export type DailyRow = {
  site_id: string; local_date: string; time_zone: string | null; identity_key: string; identity_kind: "PERSON" | "CODE";
  mapping_state: MappingState; emp_code: string; zk_emp_codes: string[]; bamboohr_id: string | null;
  employee_number: string | null; employee_name: string | null; department: string | null; employment_status: string | null;
  has_photo: boolean; mapping_status: MappingStatus;
  first_fingerprint_local: string | null; last_fingerprint_local: string | null; punch_count: number;
  recorded_span_minutes: number | null; single: boolean; terminal_names: string[];
  review: ReviewSummary | null; earlier_code_cases?: ReviewSummary[];
};
export type DailySummary = {
  identity_days: number; punches: number; single_fingerprint_days: number;
  verified_identity_days: number; unmapped_identity_days: number; conflict_identity_days: number;
  verified_punches: number; unmapped_punches: number; conflict_punches: number;
};
export type DailyResponse = Paged<DailyRow> & {
  date_from: string; date_to: string; time_zone: string | null; mapping: MappingFilter; summary: DailySummary;
  directory_available: boolean; can_investigate_identity?: boolean; can_manage_reviews?: boolean;
};

export type ExtremeEntry = { zk_emp_code: string; mapping_state: MappingState; local_time: string; bamboohr_id: string | null;
  employee_name: string | null; employee_number: string | null; terminal: string | null };
export type ExtremeBlock = { local_time: string; punch_time_utc: string; tied: number; entries: ExtremeEntry[] };
export type Extremes = { date: string; time_zone: string | null; earliest: ExtremeBlock | null; latest: ExtremeBlock | null };

export type Paged<T> = { total: number; page: number; page_size: number; items: T[] };

export type TodayResponse = Paged<DayActivity> & { date: string; departments: string[]; directory_available: boolean };
export type ActivityResponse = Paged<ActivityEvent> & {
  directory_available: boolean;
  mapping?: MappingFilter;
  /** Same filters without the mapping filter: recorded = verified + unmapped + conflict. */
  summary?: ActivitySummary;
  /** Identity administrators may open unmapped IDs in Identity Management. */
  can_investigate_identity?: boolean;
};

export type EmployeeRow = EmployeeRef & {
  in_directory: boolean;
  events: number;
  activity_days: number;
  review_flags: number;
  last_activity_local: string | null;
};
export type EmployeesSummary = {
  employees: number;
  with_activity: number;
  active: number;
  inactive: number;
  not_in_directory: number;
  needing_review: number;
  matched: number;
};

export type EmployeesResponse = Paged<EmployeeRow> & {
  summary?: EmployeesSummary;
  date_from: string;
  date_to: string;
  departments: string[];
  directory_available: boolean;
};

export type MappingPeriodRef = { mapping_id: number; zk_emp_code: string; valid_from: string; valid_to: string | null };

export type EmployeeDetail = {
  profile: EmployeeRef & { job_title: string | null; match_count: number };
  /** Verified ZKBioTime ID ownership periods of this team member at the site. */
  mappings?: MappingPeriodRef[];
  summary: { activity_days: number; events: number; review_flags: number };
  days: DayActivity[];
  events: ActivityEvent[];
  directory_available: boolean;
};

export type ExceptionItem = DayActivity & { reasons: { flag: ReviewFlag; reason: string }[] };
export type ExceptionsResponse = Paged<ExceptionItem> & { counts: Record<ReviewFlag, number>; directory_available: boolean; can_manage_reviews?: boolean };
export const getDailyActivity = (p: Params) => request<DailyResponse>(`${ONSITE_API}/activity/daily${qs(p)}`);

type Params = Record<string, string | number | boolean | undefined | null>;

export const getSitesInfo = () => request<OnsiteSiteInfo[]>(`${ONSITE_API}/sites`);
export const getOverview = (p: Params) => request<Overview>(`${ONSITE_API}/dashboard/overview${qs(p)}`);
export const getHourly = (p: Params) =>
  request<{ hours: HourBucket[] }>(`${ONSITE_API}/dashboard/hourly-activity${qs(p)}`);
export const getTrend = (p: Params) => request<{ days: TrendDay[] }>(`${ONSITE_API}/dashboard/activity-trend${qs(p)}`);
export const getRecent = (p: Params) => request<ActivityResponse>(`${ONSITE_API}/dashboard/recent-activity${qs(p)}`);
export const getToday = (p: Params) => request<TodayResponse>(`${ONSITE_API}/today${qs(p)}`);
export const getActivity = (p: Params) => request<ActivityResponse>(`${ONSITE_API}/activity${qs(p)}`);
export const getEmployees = (p: Params) => request<EmployeesResponse>(`${ONSITE_API}/employees${qs(p)}`);
/** Profile photo as an object URL, or null when there is none (404 is a
 *  normal answer, never an error). Fetched with the bearer token, because a
 *  plain <img src> cannot send it. */
export async function getEmployeePhoto(bamboohrId: string): Promise<string | null> {
  const resp = await authorizedFetch(`${ONSITE_API}/employees/by-id/${encodeURIComponent(bamboohrId)}/photo`);
  if (!resp.ok) return null;
  const blob = await resp.blob();
  return blob.size ? URL.createObjectURL(blob) : null;
}

/** Profile of a VERIFIED team member, addressed by BHR ID. */
export const getEmployee = (bamboohrId: string, p: Params) =>
  request<EmployeeDetail>(`${ONSITE_API}/employees/by-id/${encodeURIComponent(bamboohrId)}${qs(p)}`);
export const getExceptions = (p: Params) => request<ExceptionsResponse>(`${ONSITE_API}/exceptions${qs(p)}`);

export type ExportPath = "today" | "activity" | "activity/daily" | "employees" | "exceptions" | "dashboard/overview";

/** Downloads a server-generated .xlsx with the caller's bearer token (a plain
 *  link would not send it). The server re-applies scope and every filter. */
export async function downloadExport(path: ExportPath, p: Params): Promise<void> {
  const resp = await authorizedFetch(`${ONSITE_API}/${path}/export${qs(p)}`);
  if (!resp.ok) {
    let detail = `Export failed (${resp.status}). Please try again.`;
    try {
      const body = await resp.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the generic message */
    }
    throw new Error(detail);
  }
  const match = /filename="([^"]+)"/.exec(resp.headers.get("Content-Disposition") ?? "");
  const url = URL.createObjectURL(await resp.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = match?.[1] ?? "Diji-Onsite_Export.xlsx";
  a.click();
  URL.revokeObjectURL(url);
}
