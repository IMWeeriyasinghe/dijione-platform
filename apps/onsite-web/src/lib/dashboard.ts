import { getToken, qs, request } from "@dijione/auth-client";
import { ONSITE_API } from "./api";
import type { FeedState, IdentityClass } from "./types";

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

export type OnsiteSiteInfo = {
  site_id: string;
  name: string;
  time_zone: string | null;
  today: string;
  first_activity_date: string | null;
  last_activity_date: string | null;
  terminals: string[];
};

export type Overview = {
  site_id: string;
  date: string;
  time_zone: string | null;
  directory_available: boolean;
  kpis: {
    employees_with_activity: number;
    total_events: number;
    employees_needing_review: number;
    single_punch_employees: number;
    unmatched_codes: number;
    feed_state: FeedState | null;
  };
  review_breakdown: Record<ReviewFlag, number>;
  last_successful_sync_at: string | null;
  latest_received_utc: string | null;
  agent_heartbeat_utc: string | null;
};

export type HourBucket = { hour: number; events: number; employees: number };
export type TrendDay = { date: string; events: number; employees: number };

export type EmployeeRef = {
  emp_code: string;
  employee_name: string | null;
  department: string | null;
  employment_status?: string | null;
  identity_class: IdentityClass | null;
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
};

export type DayActivity = {
  local_date: string;
  emp_code: string;
  employee_name?: string | null;
  department?: string | null;
  first_activity_local: string | null;
  latest_activity_local: string | null;
  punch_count: number;
  span_minutes: number;
  terminal_names: string[];
  identity_class: IdentityClass | null;
  flags: ReviewFlag[];
};

export type Paged<T> = { total: number; page: number; page_size: number; items: T[] };

export type TodayResponse = Paged<DayActivity> & { date: string; departments: string[]; directory_available: boolean };
export type ActivityResponse = Paged<ActivityEvent> & { directory_available: boolean };

export type EmployeeRow = EmployeeRef & {
  in_directory: boolean;
  events: number;
  activity_days: number;
  review_flags: number;
  last_activity_local: string | null;
};
export type EmployeesResponse = Paged<EmployeeRow> & {
  date_from: string;
  date_to: string;
  departments: string[];
  directory_available: boolean;
};

export type EmployeeDetail = {
  profile: EmployeeRef & { job_title: string | null; match_count: number };
  summary: { activity_days: number; events: number; review_flags: number };
  days: DayActivity[];
  events: ActivityEvent[];
  directory_available: boolean;
};

export type ExceptionItem = DayActivity & { reasons: { flag: ReviewFlag; reason: string }[] };
export type ExceptionsResponse = Paged<ExceptionItem> & { counts: Record<ReviewFlag, number>; directory_available: boolean };

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
export const getEmployee = (code: string, p: Params) =>
  request<EmployeeDetail>(`${ONSITE_API}/employees/${encodeURIComponent(code)}${qs(p)}`);
export const getExceptions = (p: Params) => request<ExceptionsResponse>(`${ONSITE_API}/exceptions${qs(p)}`);

/** Downloads a CSV with the caller's bearer token (a plain link would not send it). */
export async function downloadActivityCsv(p: Params, filename: string): Promise<void> {
  const token = getToken();
  const resp = await fetch(`${ONSITE_API}/activity${qs({ ...p, format: "csv" })}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error(`Export failed (${resp.status})`);
  const url = URL.createObjectURL(await resp.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
