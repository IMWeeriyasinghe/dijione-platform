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

// --- DijiBirthday (Phase C) -------------------------------------------
// Mirrors apps/birthday-api/app/schemas/{order,dashboard,config}.py.

export const MODULE_BIRTHDAY = "birthday";

export const BIRTHDAY_ADMIN = "BIRTHDAY_ADMIN";
export const BIRTHDAY_USER = "BIRTHDAY_USER";
export const BIRTHDAY_SUPPLIER = "BIRTHDAY_SUPPLIER";
export const BIRTHDAY_STAFF_ROLES = new Set([BIRTHDAY_ADMIN]);

// Semi-automation future-state plan §P — the single source of truth for
// the order-status set, imported by both birthday-web and
// birthday-supplier-web instead of each re-declaring its own literal
// array (the drift that motivated this: the two apps + the backend used
// to define this set in three separate places).
export const ORDER_STATUSES = [
  "PENDING_VERIFICATION",
  "REQUIRES_REVIEW",
  "REQUIRES_ATTENTION",
  "ON_HOLD",
  "SENT_TO_SUPPLIER",
  "CHANGE_REQUESTED",
  "CONFIRMED",
  "PREPARING",
  "OUT_FOR_DELIVERY",
  "DELIVERED",
  "COMPLETED",
  "UNABLE_TO_FULFIL",
  "CANCELLED",
] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

// Derived from the backend's order_status_service.SUPPLIER_DRIVABLE —
// kept here, imported by the supplier portal, rather than re-typed there.
export const SUPPLIER_DRIVABLE_TARGETS: Record<string, OrderStatus[]> = {
  SENT_TO_SUPPLIER: ["CONFIRMED", "CHANGE_REQUESTED", "UNABLE_TO_FULFIL"],
  CONFIRMED: ["PREPARING"],
  PREPARING: ["OUT_FOR_DELIVERY"],
  OUT_FOR_DELIVERY: ["DELIVERED"],
};

export const ADDRESS_VERIFICATION_STATUSES = [
  "NOT_CHECKED",
  "VERIFICATION_REQUESTED",
  "VERIFIED",
  "NEEDS_UPDATE",
  "NOT_APPLICABLE",
] as const;
export type AddressVerificationStatus = (typeof ADDRESS_VERIFICATION_STATUSES)[number];

export const LEAD_TIME_CLASSES = ["NORMAL", "SHORT_NOTICE", "URGENT"] as const;
export type LeadTimeClass = (typeof LEAD_TIME_CLASSES)[number];

export const ORDER_ISSUE_TYPES = [
  "CHANGE_REQUEST",
  "CANNOT_FULFIL",
  "DELIVERY_ISSUE",
  "OTHER",
] as const;
export type OrderIssueType = (typeof ORDER_ISSUE_TYPES)[number];

export type OrderEventOut = {
  id: number;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  actor_id: number | null;
  actor_type: string;
  detail: string | null;
  created_at: string;
};

export type SpecialRequirementOut = {
  id: number;
  order_id: number;
  kind: string;
  text: string;
  created_by: number | null;
  created_at: string;
};

export type SpecialRequirementCreateInput = {
  kind: string;
  text: string;
};

export type OrderIssueOut = {
  id: number;
  order_id: number;
  raised_by_type: string;
  raised_by_id: number | null;
  type: string;
  detail: string;
  status: string;
  resolution_detail: string | null;
  resolved_by: number | null;
  resolved_at: string | null;
  created_at: string;
};

export type BirthdayOrderSummary = {
  id: number;
  order_reference: string;
  employee_id: string;
  employee_number: string | null;
  employee_name: string;
  birthday_date: string;
  birthday_year: number;
  office_location: string;
  lead_time_class: string;
  status: OrderStatus;
  supplier_id: number | null;
  supplier_name: string | null;
  delivery_date: string | null;
  catalogue_item_id: number | null;
  requires_admin_review: boolean;
  exception_reason: string | null;
  verify_by: string | null;
  address_verification_status: AddressVerificationStatus;
};

export type BirthdayOrderOut = {
  id: number;
  order_reference: string;
  employee_id: string;
  employee_number: string | null;
  employee_name: string;
  employee_email: string;
  birthday_date: string;
  birthday_year: number;
  office_location: string;
  detected_at: string | null;
  lead_time_days: number;
  lead_time_class: string;
  quantity: number;
  status: OrderStatus;
  hold_reason: string | null;
  address_verification_status: AddressVerificationStatus;
  delivery_address_line1: string | null;
  delivery_address_line2: string | null;
  delivery_city: string | null;
  delivery_state_province: string | null;
  delivery_postal_code: string | null;
  delivery_country: string | null;
  delivery_address_source: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
  delivery_date: string | null;
  catalogue_item_id: number | null;
  is_manual_override: boolean;
  requires_admin_review: boolean;
  exception_reason: string | null;
  verify_by: string | null;
  retry_count: number;
  last_failure_reason: string | null;
  released_at: string | null;
  released_by: number | null;
  review_confirmed_at: string | null;
  review_confirmed_by: number | null;
  accepted_at: string | null;
  preparing_at: string | null;
  out_for_delivery_at: string | null;
  delivered_at: string | null;
  completed_at: string | null;
  created_by: number | null;
  created_at: string;
  updated_at: string;
  events: OrderEventOut[];
  special_requirements: SpecialRequirementOut[];
  issues: OrderIssueOut[];
};

export type VerifyAddressInput = {
  corrected?: boolean;
  note?: string;
};

export type VerifyAddressResponse = {
  order: BirthdayOrderOut;
  auto_released: boolean;
  flagged_reasons: string[];
};

export type ConfirmReleaseInput = {
  note?: string;
};

export type AddressVerificationUpdateInput = {
  status: string;
  note?: string;
};

export type DeliveryAddressUpdateInput = {
  delivery_address_line1?: string | null;
  delivery_address_line2?: string | null;
  delivery_city?: string | null;
  delivery_state_province?: string | null;
  delivery_postal_code?: string | null;
  delivery_country?: string | null;
};

export type BirthdayOrderCreateInput = {
  employee_id: string;
  employee_number?: string;
  employee_name: string;
  employee_email: string;
  birthday_date: string;
  office_location: string;
  quantity?: number;
  delivery_date?: string;
  special_requirements?: SpecialRequirementCreateInput[];
};

export type BirthdayOrderUpdateInput = {
  quantity?: number;
  hold_reason?: string;
  office_location?: string;
  supplier_id?: number | null;
  delivery_date?: string | null;
  catalogue_item_id?: number | null;
};

export type BirthdayOrderListResponse = {
  items: BirthdayOrderSummary[];
  total: number;
  page: number;
  page_size: number;
};

export type ReadinessCheckResponse = {
  ready: boolean;
  missing: string[];
};

export type SupplierOrderView = {
  id: number;
  order_reference: string;
  employee_name: string;
  birthday_date: string;
  delivery_date: string | null;
  office_location: string;
  quantity: number;
  catalogue_item_name: string | null;
  address_verified: boolean;
  delivery_address_line1: string | null;
  delivery_address_line2: string | null;
  delivery_city: string | null;
  delivery_state_province: string | null;
  delivery_postal_code: string | null;
  delivery_country: string | null;
  status: OrderStatus;
  special_instructions: string[];
};

export type SupplierOrderListResponse = {
  items: SupplierOrderView[];
  total: number;
  page: number;
  page_size: number;
};

export type OrderIssueCreateInput = {
  type: OrderIssueType;
  detail: string;
};

export type BirthdayDashboardSummary = {
  total_orders: number;
  by_status: Record<string, number>;
  by_lead_time_class: Record<string, number>;
  upcoming_count: number;
  exceptions_count: number;
  pending_verification_count: number;
  verification_overdue_count: number;
  requires_review_count: number;
  supplier_not_accepted_count: number;
  deliveries_today_at_risk_count: number;
};

export type BirthdayUpcomingResponse = {
  days_ahead: number;
  orders: BirthdayOrderSummary[];
};

export type UpcomingBirthdayItem = {
  employee_id: string;
  employee_number: string | null;
  display_name: string;
  birthday: string; // MM-DD, no birth year
  days_until_birthday: number;
  department: string;
  location: string;
  city: string | null;
  state_province: string | null;
  cake_order_status: string;
  order_id: number | null;
  order_reference: string | null;
  hire_date: string | null;
  eligible: boolean;
  eligibility_reason: string;
  address_verification_status: string | null;
};

export type UpcomingBirthdaysResponse = {
  days: number;
  birthdays: UpcomingBirthdayItem[];
  total: number;
  page: number;
  page_size: number;
};

export type BirthdaySummaryOut = {
  service: string;
  status: string;
  product_status: string;
  total_orders: number;
  exceptions_count: number;
  upcoming_count: number;
};

export type BirthdayDetectionConfigOut = {
  id: number;
  normal_threshold_days: number;
  short_notice_threshold_days: number;
  urgent_threshold_days: number;
  window_lookback_days: number;
  window_lookahead_days: number;
  updated_by: number | null;
};

export type BirthdayDetectionConfigUpdateInput = {
  normal_threshold_days?: number;
  short_notice_threshold_days?: number;
  urgent_threshold_days?: number;
  window_lookback_days?: number;
  window_lookahead_days?: number;
};

// --- DijiBirthday Supplier Management (Phase D) -------------------------
// Mirrors apps/birthday-api/app/schemas/supplier.py.

export type SupplierOut = {
  id: number;
  name: string;
  status: string;
  primary_contact_name: string;
  primary_contact_email: string;
  primary_contact_phone: string;
  escalation_contact_name: string;
  escalation_contact_email: string;
  lead_time_days: number;
  working_days: string;
  cutoff_time: string;
  notes: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

export type SupplierListResponse = {
  items: SupplierOut[];
  total: number;
  page: number;
  page_size: number;
};

export type SupplierCreateInput = {
  name: string;
  status?: string;
  primary_contact_name?: string;
  primary_contact_email?: string;
  primary_contact_phone?: string;
  escalation_contact_name?: string;
  escalation_contact_email?: string;
  lead_time_days?: number;
  working_days?: string;
  cutoff_time?: string;
  notes?: string;
  is_default?: boolean;
};

export type SupplierUpdateInput = {
  name?: string;
  status?: string;
  primary_contact_name?: string;
  primary_contact_email?: string;
  primary_contact_phone?: string;
  escalation_contact_name?: string;
  escalation_contact_email?: string;
  lead_time_days?: number;
  working_days?: string;
  cutoff_time?: string;
  notes?: string;
  is_default?: boolean;
};

export type SupplierLocationOut = {
  id: number;
  supplier_id: number;
  office_location: string;
  is_primary: boolean;
};

export type SupplierLocationCreateInput = {
  office_location: string;
  is_primary?: boolean;
};

export type SupplierCatalogueItemOut = {
  id: number;
  supplier_id: number;
  name: string;
  description: string;
  is_active: boolean;
  is_default: boolean;
};

export type SupplierCatalogueItemCreateInput = {
  name: string;
  description?: string;
  is_active?: boolean;
  is_default?: boolean;
};

export type SupplierCatalogueItemUpdateInput = {
  name?: string;
  description?: string;
  is_active?: boolean;
  is_default?: boolean;
};

export type SupplierUserOut = {
  id: number;
  supplier_id: number;
  email: string;
  full_name: string;
  role: string;
  status: string;
  entra_object_id: string | null;
  created_at: string;
  updated_at: string;
};

export type SupplierUserCreateInput = {
  email: string;
  full_name?: string;
  role?: string;
  status?: string;
};

export type SupplierUserUpdateInput = {
  email?: string;
  full_name?: string;
  role?: string;
  status?: string;
  entra_object_id?: string | null;
};

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

// --- DijiOne standard source-sync framework -----------------------------
export type SyncStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "PARTIAL" | "FAILED";
export type SyncTriggerType = "SCHEDULED" | "AD_HOC";

export const SYNC_TERMINAL_STATUSES: SyncStatus[] = ["SUCCEEDED", "PARTIAL", "FAILED"];

export type SyncRunSummary = {
  run_id: string;
  provider: string;
  status: SyncStatus;
  trigger_type: SyncTriggerType;
  requested_by_application: string;
  requested_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  records_read: number;
  records_created: number;
  records_updated: number;
  records_unchanged: number;
  error_summary: string | null;
};

export type SourceFreshness = {
  provider: string;
  last_successful_sync_at: string | null;
  latest_run: SyncRunSummary | null;
};
