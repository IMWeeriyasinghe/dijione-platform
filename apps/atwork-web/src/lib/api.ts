"use client";

import { ApiError, getToken, qs } from "@dijione/auth-client";

// Same token and relative-path conventions as the shared request helper, which
// does not expose the backend's machine-readable error code.
export class AtworkError extends ApiError {
  code: string | null;
  constructor(status: number, message: string, code: string | null) {
    super(status, message);
    this.code = code;
  }
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...init, headers });
  if (res.ok) return res;
  let detail = res.statusText;
  let code: string | null = null;
  try {
    const body = await res.json();
    code = typeof body.code === "string" ? body.code : null;
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) detail = "Please check the values you entered.";
  } catch {
    // no JSON body
  }
  throw new AtworkError(res.status, detail, code);
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await send(path, init)).json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) => json<T>(path, { method: "POST", body: JSON.stringify(body) });

export type WorkMode = "OFFICE" | "REMOTE" | "CLIENT_SITE";
export type AttendanceState = "NOT_CHECKED_IN" | "WORKING" | "ON_BREAK";
/** Confirmed time; provisional_seconds is unverified time kept out of it. */
export type Totals = { gross_seconds: number; break_seconds: number; net_seconds: number; provisional_seconds?: number };
export type DayTotals = Totals & { date: string };
export type Break = { id: string; started_at: string; ended_at: string | null };
export type Session = {
  id: string; work_mode: WorkMode; status: "OPEN" | "COMPLETED"; check_in_at: string; check_out_at: string | null;
  time_zone: string; origin: string; correction_count: number; breaks: Break[]; totals: Totals;
  /** Longer than the missed check-out threshold and not yet confirmed by Management. */
  unverified?: boolean;
};
export type Status = { state: AttendanceState; server_time: string; time_zone: string; session: Session | null };
export type ActionResult = { replayed: boolean; state: AttendanceState; server_time: string; session: Session };
export type Today = { date: string; time_zone: string; server_time: string; session_count: number; totals: Totals; sessions: Session[] };
export type History = {
  date_from: string; date_to: string; time_zone: string; total: number; limit: number; offset: number;
  daily_totals: DayTotals[]; sessions: Session[];
};
export type Policy = {
  enabled_work_modes: WorkMode[]; business_time_zone: string; missed_checkout_hours: number;
  time_format: "24h" | "12h"; default_history_days: number; server_time: string;
};
export type ProposedBreak = { started_at: string; ended_at: string };
export type CorrectionValues = {
  status?: string; work_mode: WorkMode; check_in_at: string; check_out_at: string | null;
  breaks: { started_at: string; ended_at: string | null }[];
};
export type CorrectionStatus = "PENDING" | "APPROVED" | "REJECTED" | "WITHDRAWN";
export type Correction = {
  id: string; platform_user_id: number; employee_name: string; kind: "AMEND" | "CREATE_MISSING"; status: CorrectionStatus;
  session_id: string | null; reason: string; original: CorrectionValues | null; proposed: CorrectionValues;
  reviewer_name: string | null; reviewed_at: string | null; decision_note: string | null;
  created_at: string; updated_at: string; can_decide: boolean;
};
export type Page<T> = { total: number; limit: number; offset: number; items: T[] };
export type CorrectionInput = {
  client_request_id: string; session_id?: string; reason: string; work_mode?: WorkMode;
  check_in_at?: string; check_out_at?: string; breaks?: ProposedBreak[];
};
export type LiveEmployee = { platform_user_id: number; employee_name: string; state: "WORKING" | "ON_BREAK"; session: Session; overdue: boolean };
export type MissedCheckout = {
  session_id: string; platform_user_id: number; employee_name: string; work_mode: WorkMode;
  check_in_at: string; open_seconds: number; break_open: boolean;
};
export type Overview = {
  date: string; time_zone: string; server_time: string; working_count: number; on_break_count: number;
  completed_today: number; exception_count: number; pending_corrections: number | null; totals: Totals;
  working: LiveEmployee[]; on_break: LiveEmployee[];
  completed: { platform_user_id: number; employee_name: string; session: Session }[];
  exceptions: MissedCheckout[];
};
export type Employee = { platform_user_id: number; employee_name: string; email: string | null; state: AttendanceState };
export type EmployeeHistory = Omit<History, never> & { employee: Employee };
export type AuditEvent = {
  id: string; action: string; entity_type: string; entity_id: string; session_id: string | null;
  actor_user_id: number; actor_name: string; subject_user_id: number; subject_name: string;
  occurred_at: string; before_state: Record<string, unknown> | null; after_state: Record<string, unknown> | null;
};
export type ReportSummary = {
  date_from: string; date_to: string; time_zone: string; session_count: number; totals: Totals;
  by_work_mode: (Totals & { work_mode: WorkMode })[]; by_day: DayTotals[];
  employee_total: number; limit: number; offset: number;
  by_employee: { platform_user_id: number; employee_name: string; session_count: number; totals: Totals }[];
};
export type Settings = {
  enabled_work_modes: WorkMode[]; business_time_zone: string; missed_checkout_hours: number;
  time_format: "24h" | "12h"; default_history_days: number; version: number;
};
export type ReportFilters = { date_from?: string; date_to?: string; user_id?: string; work_mode?: string };
export type RangeParams = { date_from?: string; date_to?: string; limit?: number; offset?: number };

const A = "/api/atwork/attendance";
const C = "/api/atwork/corrections";
const M = "/api/atwork/management";

export const attendance = {
  policy: () => json<Policy>(`${A}/policy`),
  status: () => json<Status>(`${A}/status`),
  today: () => json<Today>(`${A}/today`),
  history: (p: RangeParams) => json<History>(`${A}/history${qs(p)}`),
  session: (id: string) => json<Session>(`${A}/sessions/${encodeURIComponent(id)}`),
  checkIn: (work_mode: WorkMode, client_request_id: string) => post<ActionResult>(`${A}/check-in`, { work_mode, client_request_id }),
  startBreak: (client_request_id: string) => post<ActionResult>(`${A}/breaks/start`, { client_request_id }),
  endBreak: (client_request_id: string) => post<ActionResult>(`${A}/breaks/end`, { client_request_id }),
  checkOut: (client_request_id: string) => post<ActionResult>(`${A}/check-out`, { client_request_id }),
};

export const corrections = {
  list: (p: { status?: string; limit?: number; offset?: number }) => json<Page<Correction>>(`${C}${qs(p)}`),
  get: (id: string) => json<Correction>(`${C}/${encodeURIComponent(id)}`),
  submit: (body: CorrectionInput) => post<Correction>(C, body),
  withdraw: (id: string) => post<Correction>(`${C}/${encodeURIComponent(id)}/withdraw`, {}),
};

export const management = {
  overview: () => json<Overview>(`${M}/overview`),
  employees: (p: { q?: string; limit?: number; offset?: number }) => json<Page<Employee>>(`${M}/employees${qs(p)}`),
  employeeHistory: (id: string, p: RangeParams) => json<EmployeeHistory>(`${M}/employees/${encodeURIComponent(id)}/attendance${qs(p)}`),
  session: (id: string) => json<{ employee: Employee; session: Session }>(`${M}/sessions/${encodeURIComponent(id)}`),
  corrections: (p: { status?: string; limit?: number; offset?: number }) => json<Page<Correction>>(`${M}/corrections${qs(p)}`),
  correction: (id: string) => json<Correction>(`${M}/corrections/${encodeURIComponent(id)}`),
  approve: (id: string, note?: string) => post<Correction>(`${M}/corrections/${encodeURIComponent(id)}/approve`, { note: note || null }),
  reject: (id: string, reason: string) => post<Correction>(`${M}/corrections/${encodeURIComponent(id)}/reject`, { reason }),
  audit: (p: { action?: string; user_id?: string; session_id?: string; date_from?: string; date_to?: string; limit?: number; offset?: number }) =>
    json<Page<AuditEvent>>(`${M}/audit${qs(p)}`),
  report: (p: ReportFilters & { limit?: number; offset?: number }) => json<ReportSummary>(`${M}/reports/summary${qs(p)}`),
  missed: (p: ReportFilters) => json<{ threshold_hours: number; total: number; items: MissedCheckout[] }>(`${M}/reports/missed-checkouts${qs(p)}`),
  correctionReport: (p: ReportFilters) => json<{ total: number; by_status: Record<string, number> }>(`${M}/reports/corrections${qs(p)}`),
  settings: () => json<Settings>(`${M}/settings`),
  saveSettings: (body: Settings) => json<Settings>(`${M}/settings`, { method: "PUT", body: JSON.stringify(body) }),
  async download(report: string, format: "csv" | "xlsx", filters: ReportFilters) {
    const res = await send(`${M}/reports/export${qs({ report, format, ...filters })}`);
    const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? `dijiatwork-${report}.${format}`;
    const url = URL.createObjectURL(await res.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
  },
};

const MESSAGES: Record<string, string> = {
  ALREADY_CHECKED_IN: "You are already checked in. Your status has been refreshed.",
  NOT_CHECKED_IN: "You are not checked in. Your status has been refreshed.",
  BREAK_ALREADY_ACTIVE: "You are already on a break.",
  NO_ACTIVE_BREAK: "You are not on a break.",
  BREAK_STILL_OPEN: "End your break before checking out.",
  IDEMPOTENCY_CONFLICT: "That action conflicted with an earlier attempt. Please try again.",
  TIMELINE_CONFLICT: "The server clock is behind your latest record. Please try again shortly.",
  CONCURRENT_UPDATE: "Another change was in progress. Please try again.",
  WORK_MODE_DISABLED: "That work mode is not currently available.",
  SESSION_NOT_FOUND: "That attendance session could not be found.",
  CORRECTION_ALREADY_PENDING: "A pending request already covers this session or these times.",
  CORRECTION_NO_CHANGES: "Your proposed values match the current record.",
  SESSION_OVERLAP: "These times overlap another attendance session.",
  CORRECTION_STALE: "The session changed after this request was made. Reject it and ask the employee for a new one.",
  CORRECTION_NOT_PENDING: "This request has already been decided or withdrawn.",
  SELF_DECISION_FORBIDDEN: "You cannot decide a correction to your own attendance.",
  SETTINGS_CONFLICT: "Someone else changed the settings. Reload them and try again.",
};

/** A network failure or 5xx: the server may or may not have applied the action. */
export function isUncertain(error: unknown): boolean {
  return !(error instanceof ApiError) || error.status >= 500;
}

export function errorMessage(error: unknown): string {
  if (error instanceof AtworkError && error.code && MESSAGES[error.code]) return MESSAGES[error.code];
  if (error instanceof ApiError) {
    if (error.status === 401) return "Your session has expired. Please sign in again.";
    if (error.status === 403) return error.message.startsWith("Missing") ? "You do not have permission to do this." : error.message;
    if (error.status >= 500) return "DijiAtWork could not complete this. Please try again.";
    return error.message;
  }
  return "We could not reach DijiAtWork. Check your connection and try again.";
}

export function newRequestId(): string {
  return crypto.randomUUID();
}
