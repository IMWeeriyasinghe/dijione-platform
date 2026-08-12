import type {
  AdminDashboardOut,
  AdminModuleOut,
  AdminPermissionOut,
  AdminRoleOut,
  AdminUserOut,
  ApplicationOut,
  AuditLogOut,
  CandidateOut,
  ClientDashboardOut,
  ClientInterviewOut,
  ClientOut,
  ClientPortfolioOut,
  ClientSafeCandidateOut,
  ClientScope,
  CurrentUser,
  DevPersona,
  DocumentOut,
  EffectiveAccessOut,
  InterviewOut,
  MessageOut,
  ModuleOut,
  NotificationOut,
  TaDashboardOut,
  TalentRequestCreateInput,
  TalentRequestOut,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_STORAGE_KEY = "dijione.devToken";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response had no JSON body
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

// --- Auth -------------------------------------------------------------
export const listDevPersonas = () => request<DevPersona[]>("/api/auth/dev-personas");
export const devLogin = (persona_key: string) =>
  request<{ access_token: string; user: CurrentUser }>("/api/auth/dev-login", {
    method: "POST",
    body: JSON.stringify({ persona_key }),
  });
export const getMe = () => request<CurrentUser>("/api/auth/me");

// --- Platform -----------------------------------------------------------
export const listModules = () => request<ModuleOut[]>("/api/modules");
export const listNotifications = (unreadOnly = false) =>
  request<NotificationOut[]>(`/api/notifications${qs({ unread_only: unreadOnly })}`);
export const markNotificationRead = (id: number) =>
  request<{ status: string }>(`/api/notifications/${id}/read`, { method: "POST" });

// --- Talent: Clients ------------------------------------------------------
export const listClientPortfolios = () => request<ClientPortfolioOut[]>("/api/talent/clients");
export const getClient = (id: number) => request<ClientOut>(`/api/talent/clients/${id}`);

// --- Talent: Requests -------------------------------------------------
export const listTalentRequests = (params: {
  search?: string;
  stage?: string;
  status_filter?: string;
  client_id?: number;
} = {}) => request<TalentRequestOut[]>(`/api/talent/requests${qs(params)}`);
export const getTalentRequest = (id: number) =>
  request<TalentRequestOut>(`/api/talent/requests/${id}`);
export const createTalentRequest = (payload: TalentRequestCreateInput) =>
  request<TalentRequestOut>("/api/talent/requests", { method: "POST", body: JSON.stringify(payload) });
export const reviewTalentRequest = (id: number, decision: string, reason: string) =>
  request<TalentRequestOut>(`/api/talent/requests/${id}/review`, {
    method: "POST",
    body: JSON.stringify({ decision, reason }),
  });
export const updateTalentRequestStage = (
  id: number,
  stage: string,
  client_safe_status_text?: string
) =>
  request<TalentRequestOut>(`/api/talent/requests/${id}/stage`, {
    method: "POST",
    body: JSON.stringify({ stage, client_safe_status_text }),
  });
export const updateTalentRequestTaStatus = (id: number, ta_status: string) =>
  request<TalentRequestOut>(`/api/talent/requests/${id}/ta-status`, {
    method: "POST",
    body: JSON.stringify({ ta_status }),
  });

// --- Talent: Candidates -------------------------------------------------
export const listCandidates = (search?: string) =>
  request<CandidateOut[]>(`/api/talent/candidates${qs({ search })}`);
export const getCandidate = (id: number) => request<CandidateOut>(`/api/talent/candidates/${id}`);
export const createCandidate = (payload: {
  full_name: string;
  email: string;
  phone?: string;
  professional_title?: string;
  summary?: string;
  location?: string;
  skills?: string[];
  source?: string;
}) => request<CandidateOut>("/api/talent/candidates", { method: "POST", body: JSON.stringify(payload) });
export const listRequestCandidates = (requestId: number) =>
  request<ClientSafeCandidateOut[]>(`/api/talent/requests/${requestId}/candidates`);

// --- Talent: Applications -------------------------------------------------
export const listApplications = (params: { search?: string; talent_request_id?: number } = {}) =>
  request<ApplicationOut[]>(`/api/talent/applications${qs(params)}`);
export const createApplication = (payload: {
  candidate_id: number;
  talent_request_id: number;
  current_stage?: string;
}) => request<ApplicationOut>("/api/talent/applications", { method: "POST", body: JSON.stringify(payload) });
export const updateApplicationStage = (id: number, stage: string) =>
  request<ApplicationOut>(`/api/talent/applications/${id}/stage`, {
    method: "PATCH",
    body: JSON.stringify({ stage }),
  });
export const updateApplicationStatus = (id: number, status: string, rejection_reason = "") =>
  request<ApplicationOut>(`/api/talent/applications/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, rejection_reason }),
  });
export const updateApplicationScore = (id: number, score: number, recruiter_notes = "") =>
  request<ApplicationOut>(`/api/talent/applications/${id}/score`, {
    method: "PATCH",
    body: JSON.stringify({ score, recruiter_notes }),
  });
export const updateApplicationVisibility = (
  id: number,
  is_client_visible: boolean,
  client_visible_notes = ""
) =>
  request<ApplicationOut>(`/api/talent/applications/${id}/visibility`, {
    method: "PATCH",
    body: JSON.stringify({ is_client_visible, client_visible_notes }),
  });

// --- Talent: Interviews -------------------------------------------------
export const listInterviews = () =>
  request<(InterviewOut | ClientInterviewOut)[]>("/api/talent/interviews");
export const createInterview = (payload: {
  application_id: number;
  scheduled_at: string;
  interview_type?: string;
  meeting_link?: string;
  client_visible?: boolean;
  notes?: string;
}) => request<InterviewOut>("/api/talent/interviews", { method: "POST", body: JSON.stringify(payload) });
export const updateInterviewStatus = (id: number, status: string, notes = "") =>
  request<InterviewOut>(`/api/talent/interviews/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, notes }),
  });

// --- Talent: Messages / Documents (request-scoped) -------------------------
export const listMessages = (requestId: number) =>
  request<MessageOut[]>(`/api/talent/requests/${requestId}/messages`);
export const sendMessage = (requestId: number, body: string) =>
  request<MessageOut>(`/api/talent/requests/${requestId}/messages`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
export const listDocuments = (requestId: number) =>
  request<DocumentOut[]>(`/api/talent/requests/${requestId}/documents`);
export const uploadDocument = (requestId: number, file_name: string, category = "OTHER") =>
  request<DocumentOut>(`/api/talent/requests/${requestId}/documents`, {
    method: "POST",
    body: JSON.stringify({ talent_request_id: requestId, file_name, category }),
  });

// --- Talent: Dashboards -------------------------------------------------
export const getClientDashboard = () => request<ClientDashboardOut>("/api/talent/dashboard/client");
export const getTaDashboard = () => request<TaDashboardOut>("/api/talent/ta/dashboard");

// --- DijiOne Admin Center (Phase 2) -------------------------------------
export const getAdminDashboard = () => request<AdminDashboardOut>("/api/admin/dashboard");
export const listAdminUsers = () => request<AdminUserOut[]>("/api/admin/users");
export const getAdminUser = (id: number) => request<AdminUserOut>(`/api/admin/users/${id}`);
export const getEffectiveAccess = (id: number) =>
  request<EffectiveAccessOut>(`/api/admin/users/${id}/effective-access`);
export const updateUserStatus = (id: number, is_active: boolean) =>
  request<AdminUserOut>(`/api/admin/users/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ is_active }),
  });
export const updatePlatformRole = (id: number, platform_role: string) =>
  request<AdminUserOut>(`/api/admin/users/${id}/platform-role`, {
    method: "PATCH",
    body: JSON.stringify({ platform_role }),
  });
export const upsertModuleAssignment = (
  userId: number,
  moduleKey: string,
  payload: { role: string; enabled: boolean; client_scope?: ClientScope | { all_clients: boolean; client_ids: number[] } }
) =>
  request<AdminUserOut>(`/api/admin/users/${userId}/modules/${moduleKey}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
export const removeModuleAssignment = (userId: number, moduleKey: string) =>
  request<AdminUserOut>(`/api/admin/users/${userId}/modules/${moduleKey}`, { method: "DELETE" });
export const listAdminClients = () => request<{ id: number; name: string }[]>("/api/admin/clients");
export const listAdminModules = () => request<AdminModuleOut[]>("/api/admin/modules");
export const listAdminRoles = () => request<AdminRoleOut[]>("/api/admin/roles");
export const listAdminPermissions = () => request<AdminPermissionOut[]>("/api/admin/permissions");
export const listAdminAudit = (params: { entity_type?: string; limit?: number } = {}) =>
  request<AuditLogOut[]>(`/api/admin/audit${qs(params)}`);

// --- Integrations (read-only status) ---------------------------------
export const getLeverStatus = () => request<Record<string, unknown>>("/api/integrations/lever/status");
export const getHubspotStatus = () =>
  request<Record<string, unknown>>("/api/integrations/hubspot/status");
export const listIntegrationEvents = () =>
  request<Record<string, unknown>[]>("/api/integrations/events");
