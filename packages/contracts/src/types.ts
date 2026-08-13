// Mirrors apps/api/app/schemas/*.py — kept in sync by hand for the MVP.
// If/when the API surface grows, consider generating these from the
// FastAPI OpenAPI schema instead.

export type ModuleRole = {
  module_key: string;
  role: string;
  client_id: number | null;
  enabled?: boolean;
};

export type CurrentUser = {
  id: number;
  email: string;
  full_name: string;
  title: string | null;
  platform_role: "PLATFORM_USER" | "PLATFORM_ADMIN" | "SUPER_ADMIN";
  avatar_color: string | null;
  module_roles: ModuleRole[];
  platform_permissions: string[];
};

export type DevPersona = {
  persona_key: string;
  full_name: string;
  title: string | null;
  platform_role: string;
  module_roles: ModuleRole[];
  avatar_color: string | null;
};

export type ModuleOut = {
  id: number;
  key: string;
  name: string;
  description: string;
  icon: string;
  route: string;
  status: string;
  enabled: boolean;
  display_order: number;
};

export type NotificationOut = {
  id: number;
  type: string;
  title: string;
  body: string;
  is_read: boolean;
  related_entity_type: string | null;
  related_entity_id: number | null;
  created_at: string;
};

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

export const TALENT_CLIENT = "TALENT_CLIENT";
export const TA_MEMBER = "TA_MEMBER";
export const CUSTOMER_SUCCESS = "CUSTOMER_SUCCESS";
export const TA_MANAGER = "TA_MANAGER";
export const STAFF_ROLES = new Set([TA_MEMBER, CUSTOMER_SUCCESS, TA_MANAGER]);

export const MODULE_TALENT_FLOW = "talent-flow";

// --- DijiOne Admin Center (Phase 2) ----------------------------------------
// Mirrors apps/api/app/schemas/admin.py.

export type ClientScope = {
  all_clients: boolean;
  client_ids: number[];
  client_names: string[];
};

export type ModuleAssignmentOut = {
  module_key: string;
  module_name: string;
  role: string;
  role_name: string;
  enabled: boolean;
  client_scope: ClientScope | null;
};

export type AdminUserOut = {
  id: number;
  email: string;
  full_name: string;
  title: string | null;
  platform_role: string;
  is_active: boolean;
  identity_provider: string;
  entra_object_id: string | null;
  last_login_at: string | null;
  created_at: string;
  module_assignments: ModuleAssignmentOut[];
};

export type AdminModuleOut = {
  id: number;
  key: string;
  name: string;
  description: string;
  icon: string;
  route: string;
  status: string;
  enabled: boolean;
  display_order: number;
  user_count: number;
};

export type AdminRoleOut = {
  id: number;
  module_key: string | null;
  key: string;
  name: string;
  description: string;
  is_system: boolean;
  permission_count: number;
  user_count: number;
};

export type AdminPermissionOut = {
  id: number;
  key: string;
  name: string;
  description: string;
  module_key: string | null;
  category: string;
};

export type AuditLogOut = {
  id: number;
  actor_id: number | null;
  actor_name: string | null;
  action: string;
  entity_type: string;
  entity_id: number;
  previous_state: string;
  new_state: string;
  metadata: string;
  created_at: string;
};

export type AccessSourceOut = {
  type: "DIRECT" | "GROUP";
  role: string | null;
  group_id: number | null;
  group_name: string | null;
};

export type EffectiveModuleAccessOut = {
  module_key: string;
  module_name: string;
  enabled: boolean;
  role: string;
  role_name: string;
  client_scope: ClientScope;
  permissions: string[];
  sources: AccessSourceOut[];
};

export type EffectiveAccessOut = {
  user_id: number;
  full_name: string;
  platform_role: string;
  is_active: boolean;
  platform_permissions: string[];
  modules: EffectiveModuleAccessOut[];
};

export type GroupMemberOut = {
  user_id: number;
  email: string;
  full_name: string;
};

export type GroupModuleAssignmentOut = {
  module_key: string;
  module_name: string;
  role: string;
  role_name: string;
  enabled: boolean;
  client_scope: ClientScope | null;
};

export type AccessGroupOut = {
  id: number;
  key: string;
  display_name: string;
  description: string;
  status: string;
  group_type: string;
  member_count: number;
  module_count: number;
  created_at: string;
  updated_at: string;
};

export type AccessGroupDetailOut = {
  id: number;
  key: string;
  display_name: string;
  description: string;
  status: string;
  group_type: string;
  created_at: string;
  updated_at: string;
  members: GroupMemberOut[];
  module_assignments: GroupModuleAssignmentOut[];
};

export type ApplicationAssignedUserOut = {
  user_id: number;
  email: string;
  full_name: string;
  role: string;
  role_name: string;
  enabled: boolean;
  client_scope: ClientScope;
};

export type ApplicationAssignedGroupOut = {
  group_id: number;
  group_key: string;
  group_name: string;
  role: string;
  role_name: string;
  enabled: boolean;
  client_scope: ClientScope;
};

export type ApplicationDetailOut = {
  module_key: string;
  module_name: string;
  description: string;
  status: string;
  enabled: boolean;
  assigned_users: ApplicationAssignedUserOut[];
  assigned_groups: ApplicationAssignedGroupOut[];
  direct_user_count: number;
  group_count: number;
};

export type AdminDashboardOut = {
  total_users: number;
  active_users: number;
  platform_admins: number;
  super_admins: number;
  active_modules: number;
  pending_talent_requests: number;
};

export const PLATFORM_ROLE_LABELS: Record<string, string> = {
  SUPER_ADMIN: "Super Admin",
  PLATFORM_ADMIN: "Platform Admin",
  PLATFORM_USER: "Platform User",
};
