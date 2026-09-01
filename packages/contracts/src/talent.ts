// talent
// DijiTalentFlow — clients, talent requests, candidates, applications,
// interviews, messages, documents. Mirrors apps/talent-api/app/schemas/*.py.
// Published contract: a breaking change to a shape here needs a version bump
// (packages/contracts's own package.json), since every *-web app imports it.

export type ClientOut = {
  id: number;
  name: string;
  industry: string | null;
  account_manager: string | null;
  status: string;
  created_at: string;
};

export type ClientPortfolioOut = ClientOut & {
  total_requests: number;
  active_requests: number;
};

export type StageProgress = {
  stage: string;
  label: string;
  state: "DONE" | "CURRENT" | "UPCOMING";
};

export type TalentRequestOut = {
  id: number;
  request_code: string;
  client_id: number;
  client_name: string | null;
  designation: string;
  description: string;
  required_skills: string[];
  seniority: string;
  location: string;
  engagement_type: string;
  target_start_date: string | null;
  notes: string;
  current_stage: string;
  lifecycle_status: string;
  customer_success_status: string;
  ta_status: string;
  client_safe_status_text: string;
  priority: string;
  progress_percent: number;
  stage_timeline: StageProgress[];
  active_application_count: number;
  created_at: string;
  updated_at: string;
};

export type TalentRequestCreateInput = {
  designation: string;
  description: string;
  required_skills: string[];
  seniority?: string;
  location?: string;
  engagement_type?: string;
  target_start_date?: string | null;
  notes?: string;
};

export type CandidateApplicationSummary = {
  application_id: number;
  client_name: string;
  designation: string;
  current_stage: string;
  status: string;
};

export type CandidateOut = {
  id: number;
  full_name: string;
  email: string;
  phone: string;
  professional_title: string;
  summary: string;
  location: string;
  availability_status: string;
  skills: string[];
  cv_reference: string;
  source: string;
  applications: CandidateApplicationSummary[];
  created_at: string;
};

export type ClientSafeCandidateOut = {
  application_id: number;
  full_name: string;
  professional_title: string;
  skills: string[];
  relevant_experience_summary: string;
  current_stage: string;
  upcoming_interview_status: string | null;
};

export type ApplicationOut = {
  id: number;
  candidate_id: number;
  candidate_name: string;
  talent_request_id: number;
  client_name: string;
  designation: string;
  current_stage: string;
  status: string;
  score: number | null;
  recruiter_notes: string;
  client_visible_notes: string;
  rejection_reason: string;
  is_client_visible: boolean;
  created_at: string;
  updated_at: string;
};

export type InterviewOut = {
  id: number;
  application_id: number;
  talent_request_id: number;
  candidate_name: string;
  client_name: string;
  designation: string;
  scheduled_at: string;
  interview_type: string;
  status: string;
  meeting_link: string;
  client_visible: boolean;
  notes: string;
};

export type ClientInterviewOut = {
  id: number;
  talent_request_id: number;
  candidate_name: string;
  designation: string;
  scheduled_at: string;
  interview_type: string;
  status: string;
  meeting_link: string | null;
};

export type MessageOut = {
  id: number;
  talent_request_id: number;
  sender_id: number;
  sender_name: string;
  sender_role: string;
  body: string;
  created_at: string;
};

export type DocumentOut = {
  id: number;
  talent_request_id: number;
  file_name: string;
  category: string;
  uploaded_by: number;
  uploaded_by_name: string;
  storage_reference: string;
  created_at: string;
};

export type ClientDashboardOut = {
  active_requests: number;
  candidates_in_process: number;
  interviews_this_week: number;
  offers_in_progress: number;
  requests: TalentRequestOut[];
};

export type TaDashboardOut = {
  clients: number;
  active_requests: number;
  active_applications: number;
  available_candidates: number;
  interviews_scheduled: number;
  offers_in_progress: number;
  pending_review_count: number;
  attention_requests: TalentRequestOut[];
};

// Magic-link external client access — TA grant management screen
// (apps/talent-api/app/schemas/external.py). The raw token / access URL
// exist ONLY on MagicLinkGrantCreatedOut, returned once from
// create/regenerate; the list view never carries them.
export type MagicLinkGrantOut = {
  public_id: string;
  client_id: number;
  client_name: string;
  scope_type: string;
  contact_name: string;
  contact_email: string;
  token_prefix: string;
  status: "ACTIVE" | "EXPIRED" | "REVOKED";
  issued_by_user_id: number;
  issued_at: string;
  expires_at: string;
  redeemed_at: string | null;
  last_used_at: string | null;
  use_count: number;
  revoked_at: string | null;
  revoked_by_user_id: number | null;
};

export type MagicLinkGrantCreatedOut = MagicLinkGrantOut & {
  raw_token: string;
  access_url: string;
};

export const TALENT_CLIENT = "TALENT_CLIENT";
export const TA_MEMBER = "TA_MEMBER";
export const CUSTOMER_SUCCESS = "CUSTOMER_SUCCESS";
export const TA_MANAGER = "TA_MANAGER";
export const STAFF_ROLES = new Set([TA_MEMBER, CUSTOMER_SUCCESS, TA_MANAGER]);

export const MODULE_TALENT_FLOW = "talent-flow";

