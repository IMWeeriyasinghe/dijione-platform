import type {
  ApplicationOut,
  CandidateOut,
  ClientDashboardOut,
  ClientInterviewOut,
  ClientOut,
  ClientPortfolioOut,
  ClientSafeCandidateOut,
  DocumentOut,
  InterviewOut,
  MessageOut,
  TaDashboardOut,
  TalentRequestOut,
} from "@dijione/contracts";
import { qs, request } from "@dijione/auth-client";

export { ApiError } from "@dijione/auth-client";

// --- Clients ------------------------------------------------------
export const listClientPortfolios = () => request<ClientPortfolioOut[]>("/api/talent/clients");
export const getClient = (id: number) => request<ClientOut>(`/api/talent/clients/${id}`);

// --- Requests -------------------------------------------------
export const listTalentRequests = (params: {
  search?: string;
  stage?: string;
  status_filter?: string;
  client_id?: number;
} = {}) => request<TalentRequestOut[]>(`/api/talent/requests${qs(params)}`);
export const getTalentRequest = (id: number) =>
  request<TalentRequestOut>(`/api/talent/requests/${id}`);
// NOTE: no createTalentRequest — DijiTalentFlow is not a client intake
// portal (retired 2026-09-01). The backend route still exists
// (POST /api/talent/requests) but always 403s; see
// apps/talent-api/app/api/routes/talent_requests.py.
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

// --- Candidates -------------------------------------------------
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

// --- Applications -------------------------------------------------
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

// --- Interviews -------------------------------------------------
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

// --- Messages / Documents (request-scoped) -------------------------
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

// --- Dashboards -------------------------------------------------
export const getClientDashboard = () => request<ClientDashboardOut>("/api/talent/dashboard/client");
export const getTaDashboard = () => request<TaDashboardOut>("/api/talent/ta/dashboard");

// --- Integrations (read-only status) ---------------------------------
export const getLeverStatus = () => request<Record<string, unknown>>("/api/talent/integrations/lever/status");
export const getHubspotStatus = () =>
  request<Record<string, unknown>>("/api/talent/integrations/hubspot/status");
export const listIntegrationEvents = () =>
  request<Record<string, unknown>[]>("/api/talent/integrations/events");

// --- Recruitment Source (Lever) sync -------------------------------
import type { SourceFreshness, SyncRunSummary } from "@dijione/contracts";

export const getRecruitmentFreshness = () =>
  request<SourceFreshness>("/api/talent/integrations/recruitment/freshness");

// --- Recruitment postings (staff — Recruitment Source posting -> client mapping) ---
// Posting facts are a thin local projection of recruitment-api's canonical
// DTO; the mapping fields are the DijiTalentFlow-owned trust decision.
export type PostingRow = {
  id: number;
  external_id: string;
  provider: string;
  title: string;
  state: string;
  location: string;
  archived: boolean;
  mapping_status: "UNMAPPED" | "VERIFIED" | "REJECTED";
  mapping_client_id: number | null;
  mapping_client_name: string | null;
  mapping_source: string;
  dtc_source_tag: string | null;
  dtc_client_name: string | null;
  resolution_status: string;
};

export const listRecruitmentPostings = (unresolvedOnly = false) =>
  request<PostingRow[]>(`/api/talent/postings${qs({ unresolved_only: unresolvedOnly || undefined })}`);

export const verifyPostingMapping = (postingId: number, client_id: number) =>
  request<PostingRow>(`/api/talent/postings/${postingId}/verify-mapping`, {
    method: "POST",
    body: JSON.stringify({ client_id }),
  });
export const getRecruitmentSyncRun = (runId: string) =>
  request<{ run: SyncRunSummary | null }>(`/api/talent/integrations/recruitment/sync/${runId}`);
export const requestRecruitmentSync = () =>
  request<{ run_id: string; status: string; started: boolean; message: string }>(
    "/api/talent/integrations/recruitment/sync",
    { method: "POST" },
  );
