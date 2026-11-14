import { ApiError, getToken, qs, request } from "@dijione/auth-client";
import { ONSITE_API } from "./api";
import type { Paged } from "./dashboard";

// Identity Management (admin) — mirrors onsite-api /api/onsite/admin/identity.
// Every write is re-authorised server-side (onsite.identity.manage) and
// site-scoped; this module only shapes requests and errors.
export const IDENTITY_API = `${ONSITE_API}/admin/identity`;

export type Warning = { code: string; message: string; [k: string]: unknown };

export type Mapping = {
  id: number;
  site_id: string;
  zk_emp_code: string;
  bamboohr_id: string;
  employee_name: string | null;
  employee_number: string | null;
  employee_in_directory: boolean | null;
  valid_from: string;
  valid_to: string | null;
  status: "VERIFIED" | "SUPERSEDED";
  evidence: string;
  source: "MANUAL" | "IMPORT";
  verified_by_user_id: number;
  verified_at: string | null;
  closed_reason: string | null;
  superseded_reason: string | null;
  superseded_by_id: number | null;
};

export type HistoryEvent = {
  id: number; entity_type: string; entity_id: number; action: string; actor_user_id: number; at: string | null;
  previous_json: string | null; new_json: string | null; note: string | null;
};

export type Rejection = {
  id: number; site_id: string; zk_emp_code: string; bamboohr_id: string; applies_from: string | null;
  applies_to: string | null; reason: string; status: "ACTIVE" | "WITHDRAWN"; rejected_by_user_id: number;
  rejected_at: string | null;
};

export type Hint = { bamboohr_id: string; display_name: string | null; employment_status: string | null; basis: string };

export type UnmappedRow = {
  site_id: string; zk_emp_code: string; first_seen: string; last_seen: string; event_count: number;
  activity_days: number; unmapped_events: number; unmapped_days: number; first_unmapped: string;
  last_unmapped: string; mapped_today: boolean; mapping_count: number;
  hint_employee_number_matches: Hint[]; rejections: Rejection[];
};

export type DirectoryHit = {
  bamboohr_id: string; display_name: string | null; employee_number: string | null; department: string | null;
  job_title: string | null; employment_status: string | null; hire_date: string | null;
  termination_date: string | null; has_photo: boolean; active_codes: string[];
};

export type CodeDetail = {
  site_id: string; zk_emp_code: string; directory_available: boolean; mappings: Mapping[]; rejections: Rejection[];
  hint_employee_number_matches: Hint[];
  days: { local_date: string; events: number; mapping_status: string; bamboohr_id: string | null;
    employee_name: string | null; mapping_id: number | null }[];
};

export type Readiness = {
  site_id: string; window_days: number; date_from: string; date_to: string; total_punches: number;
  identified_punches: number; identified_punch_pct: number | null; identified_employees: number;
  active_codes: number; unmapped_codes: number; unmapped_punches: number;
  high_volume_outstanding_codes: { zk_emp_code: string; unmapped_events: number; disposition: string }[];
  unresolved_conflicts: { conflict_days: number; overlapping_mappings: number; ambiguous_reassignment_days: number };
  verified_mappings: number; mappings_without_evidence: number; import_batches: HistoryEvent[];
  directory_available: boolean; decision: string;
};

export type Conflicts = {
  reused_codes: { site_id: string; zk_emp_code: string; mappings: Mapping[] }[];
  overlapping_mappings: { site_id: string; zk_emp_code: string; mappings: Mapping[] }[];
  employees_with_multiple_codes: { bamboohr_id: string; codes: string[]; mappings: Mapping[] }[];
  ambiguous_reassignment_days: { site_id: string; zk_emp_code: string; local_date: string; events: number }[];
  active_rejections: Rejection[];
  recent_events: HistoryEvent[];
};

export type ImportRow = {
  line: number; site_id?: string; zk_emp_code?: string; bamboohr_id?: string; employee_name?: string | null;
  valid_from?: string | null; valid_to?: string | null; errors: string[]; warnings: Warning[];
};
export type ImportResult = {
  dry_run?: boolean; applied?: boolean; batch_id?: string; file_sha256?: string; can_apply?: boolean;
  requires_warning_acknowledgement?: boolean; dry_run_token?: string | null;
  summary: { rows: number; rows_with_errors: number; rows_with_warnings: number; warning_codes: string[] };
  rows?: ImportRow[]; mappings?: Mapping[];
};

/** Structured error detail from onsite-api (``{error, message, warnings, ...}``). */
export type IdentityErrorDetail = {
  error?: string; message?: string; warnings?: Warning[]; unacknowledged?: string[];
  conflicts?: Mapping[]; rejections?: Rejection[]; options?: string[]; events_on_day?: number;
  rows?: ImportRow[]; summary?: ImportResult["summary"];
};

export function errorDetail(e: unknown): IdentityErrorDetail & { status?: number } {
  if (e instanceof ApiError) {
    try {
      const parsed = JSON.parse(e.message);
      if (parsed && typeof parsed === "object") return { ...parsed, status: e.status };
    } catch { /* plain text detail */ }
    return { message: e.message, status: e.status };
  }
  return { message: e instanceof Error ? e.message : "Something went wrong." };
}

type Params = Record<string, string | number | boolean | undefined | null>;
const post = <T>(path: string, body: unknown) =>
  request<T>(`${IDENTITY_API}${path}`, { method: "POST", body: JSON.stringify(body) });

export const getReadiness = (p: { site_id: string; days?: number }) => request<Readiness>(`${IDENTITY_API}/readiness${qs(p)}`);
export const getUnmapped = (p: Params) => request<Paged<UnmappedRow>>(`${IDENTITY_API}/unmapped${qs(p)}`);
export const getCodeDetail = (code: string, p: Params) =>
  request<CodeDetail>(`${IDENTITY_API}/codes/${encodeURIComponent(code)}${qs(p)}`);
export const getEvidence = (code: string, p: Params) =>
  request<{ warnings: Warning[] }>(`${IDENTITY_API}/codes/${encodeURIComponent(code)}/evidence${qs(p)}`);
export const searchDirectory = (q: string) =>
  request<Paged<DirectoryHit>>(`${IDENTITY_API}/directory/search${qs({ q, page_size: 20 })}`);
export const getMappings = (p: Params) => request<Paged<Mapping>>(`${IDENTITY_API}/mappings${qs(p)}`);
export const getMapping = (id: number) => request<Mapping & { history: HistoryEvent[] }>(`${IDENTITY_API}/mappings/${id}`);
export const getConflicts = (p: Params) => request<Conflicts>(`${IDENTITY_API}/conflicts${qs(p)}`);

export type MappingBody = {
  site_id: string; zk_emp_code: string; bamboohr_id: string; valid_from: string; valid_to?: string | null;
  evidence: string; acknowledged_warnings: string[];
};
export const createMapping = (b: MappingBody) => post<Mapping>("/mappings", b);
export const closeMapping = (id: number, b: { valid_to: string; reason: string }) => post<Mapping>(`/mappings/${id}/close`, b);
export const correctMapping = (id: number, b: {
  reason: string;
  replacement?: { bamboohr_id: string; valid_from: string; valid_to?: string | null; evidence: string; acknowledged_warnings: string[] } | null;
}) => post<{ superseded: Mapping; replacement: Mapping | null }>(`/mappings/${id}/correct`, b);
export const reassignCode = (code: string, b: {
  site_id: string; effective_from: string; reason: string; same_day_handling?: string | null;
  new: { bamboohr_id: string; valid_to?: string | null; evidence: string; acknowledged_warnings: string[] };
}) => post<{ previous: Mapping; new: Mapping; same_day_handling: string | null; unmapped_day: string | null }>(
  `/codes/${encodeURIComponent(code)}/reassign`, b);
export const rejectAssociation = (b: { site_id: string; zk_emp_code: string; bamboohr_id: string; reason: string;
  applies_from?: string | null; applies_to?: string | null }) => post<Rejection>("/rejections", b);
export const withdrawRejection = (id: number, reason: string) => post<Rejection>(`/rejections/${id}/withdraw`, { reason });

/** CSV import (multipart). ``dryRun`` validates by simulation and never persists. */
export async function importMappings(file: File, opts: { dryRun: boolean; token?: string | null; acknowledge?: boolean }): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  if (opts.token) form.append("dry_run_token", opts.token);
  form.append("acknowledge_warnings", opts.acknowledge ? "true" : "false");
  const token = getToken();
  const resp = await fetch(`${IDENTITY_API}/import${qs({ dry_run: opts.dryRun })}`, {
    method: "POST", body: form, headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(resp.status, typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? {}));
  return body as ImportResult;
}

/** Authenticated CSV download of an admin list. */
export async function downloadIdentityList(kind: "unmapped" | "mappings", p: Params = {}): Promise<void> {
  const token = getToken();
  const resp = await fetch(`${IDENTITY_API}/${kind}${qs({ ...p, format: "csv" })}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error(`Export failed (${resp.status})`);
  const url = URL.createObjectURL(await resp.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = kind === "unmapped" ? "onsite-unmapped-zkbiotime-ids.csv" : "onsite-identity-mappings.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export const WARNING_LABEL: Record<string, string> = {
  PRIOR_UNMAPPED_ACTIVITY: "Earlier punches stay unmapped",
  NO_ATTENDANCE_FOR_CODE: "No attendance recorded for this ID yet",
  STARTS_BEFORE_HIRE: "Starts before the hire date",
  EXTENDS_PAST_TERMINATION: "Extends past the termination date",
  EMPLOYEE_NOT_ACTIVE: "Team member is not active",
  EMPLOYEE_HAS_OTHER_CODES: "Team member already has other ZKBioTime ID(s)",
  CODE_REUSED: "This ZKBioTime ID was mapped to someone else before",
  ADJACENT_MAPPING: "Touches another ownership period of this ID",
};

export type Coverage = {
  site_id: string; date_from: string; date_to: string;
  ids: { observed: number; verified: number; fully_verified: number; partly_verified: number; unmapped: number };
  punches: { total: number; verified: number; unmapped: number; coverage_pct: number | null };
  verified_team_members: number;
  unresolved_conflicts: { total: number; conflict_days: number; ambiguous_reassignment_days: number; overlapping_mappings: number };
  trend: { date: string; verified_punches: number; unmapped_punches: number }[];
  top_unmapped: { zk_emp_code: string; unmapped_punches: number; unmapped_days: number; first_unmapped: string;
    last_unmapped: string; mapped_now: boolean }[];
  ingestion: { feed_state: string | null; latest_received_utc: string | null; last_successful_sync_at: string | null };
  directory_available: boolean;
};
export const getCoverage = (p: { site_id: string; date_from: string; date_to: string }) =>
  request<Coverage>(`${IDENTITY_API}/coverage${qs(p)}`);

/* ---------------------------------------------------- backlog / review state */

export type ReviewState = "AWAITING_REVIEW" | "REJECTED_ASSOCIATION" | "PARTLY_VERIFIED";

export type UnmappedSummary = {
  site_id: string; as_of: string; outstanding_ids: number; unmapped_punches: number;
  review: Record<ReviewState, number>;
  aging: { label: string; ids: number; unmapped_punches: number }[];
  recency: { label: string; ids: number; unmapped_punches: number }[];
};

export const getUnmappedSummary = (p: { site_id: string }) =>
  request<UnmappedSummary>(`${IDENTITY_API}/unmapped/summary${qs(p)}`);

/** Presentation labels for the review state of an outstanding ZKBioTime ID.
 *  A review state is not a mapping status, and none of them means resolved:
 *  an ID stays outstanding until every punch day is covered by a verified
 *  mapping. Backend values (`undispositioned`, `rejected`) are unchanged. */
export const REVIEW_STATE: Record<ReviewState, { label: string; tone: "warning" | "neutral" | "danger"; help: string }> = {
  AWAITING_REVIEW: {
    label: "Awaiting Review", tone: "warning",
    help: "No verified owner and no review outcome yet. Investigate the ID, then map it to the verified team member or record that it is not a given person.",
  },
  REJECTED_ASSOCIATION: {
    label: "Rejected Association", tone: "neutral",
    help: "A proposed team member was recorded as NOT this ID's owner. The ID itself still has no verified owner — continue the investigation.",
  },
  PARTLY_VERIFIED: {
    label: "Partly Verified", tone: "warning",
    help: "Some punch days are covered by a verified mapping and others are not. Check whether the uncovered days belong to the same team member.",
  },
};

export function reviewStateOf(r: Pick<UnmappedRow, "mapped_today" | "mapping_count" | "rejections">): ReviewState {
  if (r.mapped_today || r.mapping_count) return "PARTLY_VERIFIED";
  return r.rejections.length ? "REJECTED_ASSOCIATION" : "AWAITING_REVIEW";
}

/** Readiness `disposition` (backend: `undispositioned` | `rejected`). */
export const dispositionState = (d: string): ReviewState => (d === "rejected" ? "REJECTED_ASSOCIATION" : "AWAITING_REVIEW");
