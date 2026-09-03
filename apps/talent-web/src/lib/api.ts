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
// NOTE: no createCandidate — the Candidate master originates from the
// Recruitment Source (Lever) now, not manual entry (retired 2026-09-02).
// The backend route still exists (POST /api/talent/candidates) but always
// 403s; see apps/talent-api/app/api/routes/talent_candidates.py.
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
// NOTE: no updateApplicationStage/Status/Score — recruitment stage and
// status are Lever facts, read-only in DijiTalentFlow (the backend routes
// 403 unconditionally); score has no Lever source and is fully retired
// (the service method no longer exists). See
// apps/talent-api/app/api/routes/talent_applications.py.
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
  lever_created_at: string | null;
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
// "Manually Unmapped" (REJECTED/MANUAL) — the reconciler-immune state that
// actually survives the next DTC reconcile, unlike a naive reset to
// UNMAPPED. Reopen returns to plain UNMAPPED so DTC (or a fresh manual
// verify) can resolve it again. See apps/talent-api/app/api/routes/talent_postings.py.
export const unmapPostingMapping = (postingId: number) =>
  request<PostingRow>(`/api/talent/postings/${postingId}/unmap-mapping`, { method: "POST" });
export const reopenPostingMapping = (postingId: number) =>
  request<PostingRow>(`/api/talent/postings/${postingId}/reopen-mapping`, { method: "POST" });
export const getRecruitmentSyncRun = (runId: string) =>
  request<{ run: SyncRunSummary | null }>(`/api/talent/integrations/recruitment/sync/${runId}`);
export const requestRecruitmentSync = () =>
  request<{ run_id: string; status: string; started: boolean; message: string }>(
    "/api/talent/integrations/recruitment/sync",
    { method: "POST" },
  );

// --- Magic-link external client access (staff — TA grant management) ---
// The Client Talent Review Workspace is reached by a magic link, not a
// provisioned identity. A TA generates one link per client; the raw URL is
// shown exactly once (create/regenerate response) and never returned again.
import type { MagicLinkGrantCreatedOut, MagicLinkGrantOut } from "@dijione/contracts";

export const listMagicLinkGrants = (clientId?: number) =>
  request<MagicLinkGrantOut[]>(`/api/talent/external/grants${qs({ client_id: clientId })}`);

export const createMagicLinkGrant = (body: {
  client_id: number;
  contact_name?: string;
  contact_email?: string;
  expires_in_days?: number;
  expires_at?: string;
}) =>
  request<MagicLinkGrantCreatedOut>("/api/talent/external/grants", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const revokeMagicLinkGrant = (publicId: string) =>
  request<MagicLinkGrantOut>(`/api/talent/external/grants/${publicId}/revoke`, { method: "POST" });

export const regenerateMagicLinkGrant = (publicId: string) =>
  request<MagicLinkGrantCreatedOut>(`/api/talent/external/grants/${publicId}/regenerate`, {
    method: "POST",
  });

// Pushes expires_at forward on the SAME grant — token/public_id unchanged,
// so the client's existing URL keeps working. Extend-only (the backend
// rejects a shorter target); a revoked grant can never be extended.
export const extendMagicLinkGrant = (publicId: string, expires_at: string) =>
  request<MagicLinkGrantOut>(`/api/talent/external/grants/${publicId}/extend`, {
    method: "POST",
    body: JSON.stringify({ expires_at }),
  });
