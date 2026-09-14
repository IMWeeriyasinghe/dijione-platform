// birthday
// DijiBirthday — orders, dashboard, config, and supplier management.
// Mirrors apps/birthday-api/app/schemas/*.py.
// Published contract: a breaking change to a shape here needs a version bump
// (packages/contracts's own package.json), since every *-web app imports it.

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

// Derived from the backend's order_status_service.SUPPLIER_DRIVABLE — the
// forward fulfilment progression only. "Request a change" and "Can't
// fulfil" are NOT status buttons (Phase 1 §V.1): both go through the
// structured "Report a problem" action (OrderIssue).
export const SUPPLIER_DRIVABLE_TARGETS: Record<string, OrderStatus[]> = {
  SENT_TO_SUPPLIER: ["CONFIRMED"],
  CONFIRMED: ["PREPARING"],
  PREPARING: ["OUT_FOR_DELIVERY"],
  OUT_FOR_DELIVERY: ["DELIVERED"],
};

// --- Audience-specific status presentation (Phase 1.6 §18A) ---------------
// ONE canonical OrderStatus is the workflow/state-machine truth (unchanged,
// backend-authoritative); labels differ by audience. Never hard-code a
// status label inside a component — use these so internal-only workflow
// terminology (PENDING_VERIFICATION, REQUIRES_REVIEW, REQUIRES_ATTENTION,
// ON_HOLD) can never leak into supplier-facing UI. Those four statuses
// have no supplier label at all below because a supplier-scoped API
// response can never contain them in the first place (enforced
// server-side by SUPPLIER_VISIBLE_STATUSES) — this mapping's absence of an
// entry is a second, presentation-layer guard, not the only one.

export const INTERNAL_ORDER_STATUS_LABELS: Record<OrderStatus, string> = {
  PENDING_VERIFICATION: "Pending Verification",
  REQUIRES_REVIEW: "Requires Review",
  REQUIRES_ATTENTION: "Requires Attention",
  ON_HOLD: "On Hold",
  SENT_TO_SUPPLIER: "Sent to Supplier",
  CHANGE_REQUESTED: "Change Requested",
  CONFIRMED: "Supplier Confirmed",
  PREPARING: "Preparing",
  OUT_FOR_DELIVERY: "Out for Delivery",
  DELIVERED: "Delivered",
  COMPLETED: "Completed",
  UNABLE_TO_FULFIL: "Unable to Fulfil",
  CANCELLED: "Cancelled",
};

export function getInternalOrderStatusLabel(status: string): string {
  return INTERNAL_ORDER_STATUS_LABELS[status as OrderStatus] ?? status;
}

export const SUPPLIER_ORDER_STATUS_LABELS: Partial<Record<OrderStatus, string>> = {
  SENT_TO_SUPPLIER: "Awaiting Your Acceptance",
  CHANGE_REQUESTED: "Change Requested",
  CONFIRMED: "Accepted",
  PREPARING: "Preparing",
  OUT_FOR_DELIVERY: "Out for Delivery",
  DELIVERED: "Delivered",
  COMPLETED: "Completed",
  UNABLE_TO_FULFIL: "Unable to Fulfil",
  CANCELLED: "Cancelled",
};

export function getSupplierOrderStatusLabel(status: string): string {
  return SUPPLIER_ORDER_STATUS_LABELS[status as OrderStatus] ?? status;
}

// Supplier-dashboard-only grouping word for a status — distinct from the
// per-row label above (e.g. a SENT_TO_SUPPLIER row reads "Awaiting Your
// Acceptance" but its dashboard group is "New Orders"). Reuses
// StatusBadge's existing tone-by-canonical-status lookup unchanged — a
// status's underlying severity/colour doesn't change by audience, only
// its words do, so no separate "supplier tone" function is introduced.
export const SUPPLIER_ORDER_STATUS_GROUP: Partial<Record<OrderStatus, string>> = {
  SENT_TO_SUPPLIER: "New Orders",
  CHANGE_REQUESTED: "New Orders",
  CONFIRMED: "In Progress",
  PREPARING: "In Progress",
  OUT_FOR_DELIVERY: "In Progress",
  DELIVERED: "Done",
  COMPLETED: "Done",
  UNABLE_TO_FULFIL: "Done",
  CANCELLED: "Done",
};

export function getSupplierOrderStatusGroup(status: string): string {
  return SUPPLIER_ORDER_STATUS_GROUP[status as OrderStatus] ?? status;
}

// --- Order event log presentation (Phase 1.6 §2/§3 review round) ---------
// Centralised here for the same reason as the status labels above: the
// internal Raw Event Log must never hard-code a raw OrderEvent.event_type
// or enum value inline in a component — one lookup, reused everywhere the
// event log is rendered.

export const ORDER_EVENT_TYPE_LABELS: Record<string, string> = {
  STATUS_CHANGE: "Status Changed",
  DETECTED: "Detected",
  AUTO_RELEASED: "Auto Released",
  ADDRESS_VERIFICATION_CHANGE: "Address Verification Updated",
  SUPPLIER_ASSIGNED: "Supplier Assigned",
  EMPLOYEE_NUMBER_ASSIGNED: "Team Member ID Assigned",
  DELIVERY_DATE_ADJUSTED: "Delivery Date Adjusted",
  EXCEPTION: "Exception Raised",
  EXCEPTION_CLEARED: "Exception Cleared",
  EMAIL_SENT: "Email Sent",
  EMAIL_FAILED: "Email Failed",
  EMAIL_RETRY_EXHAUSTED: "Email Retries Exhausted",
  ORDER_CHANGED_POST_RELEASE: "Order Changed After Release",
  PORTAL_MESSAGE: "Portal Message",
  SUPPLIER_EMAIL_REPLY: "Supplier Email Reply",
  SUPPLIER_ISSUE: "Supplier Reported a Problem",
  REOPENED: "Order Reopened",
};

/** Falls back to a readable title-case rendering of an unmapped event_type
 * (e.g. a future code addition) rather than a raw underscored enum string. */
export function getOrderEventTypeLabel(eventType: string): string {
  return (
    ORDER_EVENT_TYPE_LABELS[eventType] ??
    eventType
      .toLowerCase()
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ")
  );
}

export type OrderEventTone = "success" | "warning" | "progress" | "error" | "info";

// Keyed by the event's resulting status (to_status) — the strongest signal
// for most events, since the default event_type is the generic
// "STATUS_CHANGE" and the interesting information is what it changed *to*.
const ORDER_EVENT_STATUS_TONE: Partial<Record<OrderStatus, OrderEventTone>> = {
  CONFIRMED: "success",
  DELIVERED: "success",
  COMPLETED: "success",
  PENDING_VERIFICATION: "warning",
  REQUIRES_REVIEW: "warning",
  REQUIRES_ATTENTION: "warning",
  ON_HOLD: "warning",
  PREPARING: "warning",
  CHANGE_REQUESTED: "warning",
  SENT_TO_SUPPLIER: "progress",
  OUT_FOR_DELIVERY: "progress",
  CANCELLED: "error",
  UNABLE_TO_FULFIL: "error",
};

// Keyed by event_type — used when to_status is absent, or to override a
// generic STATUS_CHANGE tone with a more specific meaning of its own.
const ORDER_EVENT_TYPE_TONE: Record<string, OrderEventTone> = {
  AUTO_RELEASED: "success",
  EMAIL_SENT: "success",
  EXCEPTION_CLEARED: "success",
  REOPENED: "warning",
  EXCEPTION: "warning",
  SUPPLIER_ISSUE: "warning",
  ORDER_CHANGED_POST_RELEASE: "warning",
  EMAIL_FAILED: "error",
  EMAIL_RETRY_EXHAUSTED: "error",
  DETECTED: "info",
  SUPPLIER_ASSIGNED: "info",
  EMPLOYEE_NUMBER_ASSIGNED: "info",
  ADDRESS_VERIFICATION_CHANGE: "info",
  DELIVERY_DATE_ADJUSTED: "info",
  PORTAL_MESSAGE: "info",
  SUPPLIER_EMAIL_REPLY: "info",
};

/** The single source of truth for an OrderEvent's semantic colour — reused
 * by the dot/icon, left accent and (never colour-only) any badge tone in
 * the Raw Event Log timeline. to_status wins when present; event_type is
 * the fallback for events that don't carry a status transition. */
export function getOrderEventTone(event: { event_type: string; to_status?: string | null }): OrderEventTone {
  if (event.to_status && ORDER_EVENT_STATUS_TONE[event.to_status as OrderStatus]) {
    return ORDER_EVENT_STATUS_TONE[event.to_status as OrderStatus]!;
  }
  return ORDER_EVENT_TYPE_TONE[event.event_type] ?? "info";
}

export const COMMUNICATION_CHANNELS = ["EMAIL", "PORTAL", "SYSTEM", "TEAMS"] as const;
export type CommunicationChannel = (typeof COMMUNICATION_CHANNELS)[number];

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
  // Phase 1.6 §17 — snapshotted at write time; null for any event written
  // before this column existed (fall back to actor_type when rendering).
  actor_display_name: string | null;
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
  employee_number?: string | null;
};

// --- Unified Timeline / communication (Phase 1 §G) --------------------
// One store (SupplierCommunication) + OrderEvent + OrderIssue markers,
// merged and audience-filtered by the backend.
export type TimelineEntryOut = {
  at: string | null;
  kind: "message" | "email" | "event" | "issue";
  channel: string | null;
  direction: "OUTBOUND" | "INBOUND" | null;
  author_type: "USER" | "SUPPLIER" | "SYSTEM" | null;
  author_id: number | null;
  title: string;
  body: string | null;
  meta: Record<string, unknown>;
};

export type OrderTimelineResponse = {
  order_id: number;
  order_reference: string;
  entries: TimelineEntryOut[];
};

export type OrderMessageCreateInput = {
  body: string;
  issue_id?: number | null;
  also_email?: boolean; // internal only
};

// --- Inbound supplier email — "Unmatched" queue (Phase 1 §1.5) --------
export type InboundEmailOut = {
  id: number;
  from_address: string;
  subject: string;
  body_preview: string;
  received_at: string | null;
  attachment_count: number;
  status: "UNMATCHED" | "LINKED" | "DISMISSED";
  reason: string;
  linked_order_id: number | null;
  created_at: string;
};

export type InboundEmailLinkInput = {
  order_id?: number;
  order_reference?: string;
  raise_issue?: boolean;
  issue_type?: OrderIssueType;
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

export type DetectionHealth = {
  last_scan_at: string | null;
  last_status: string | null;
  consecutive_deferrals: number;
  stale: boolean;
  healthy: boolean;
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
  // Phase 1.6 §6 — split from the old, misleadingly-named single
  // supplier_not_accepted_count (secretly SLA-gated).
  acceptance_awaiting_count: number;
  acceptance_overdue_count: number;
  deliveries_today_at_risk_count: number;
  on_hold_count: number;
  overdue_delivery_count: number;
  open_issues_count: number;
  unmatched_emails_count: number;
  detection_health: DetectionHealth | Record<string, never>;
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

export type SupplierUserOnboardingState =
  | "NOT_INVITED"
  | "INVITED"
  | "LINKED"
  | "ACTIVE"
  | "INACTIVE";

export type SupplierUserOut = {
  id: number;
  supplier_id: number;
  email: string;
  full_name: string;
  role: string;
  status: string;
  entra_object_id: string | null;
  invited_at: string | null;
  linked_at: string | null;
  last_login_at: string | null;
  onboarding_state: SupplierUserOnboardingState;
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
  mark_invited?: boolean;
};

export type SupplierSetupReadiness = {
  supplier_id: number;
  has_location: boolean;
  has_default_cake: boolean;
  has_active_linked_user: boolean;
  ready: boolean;
  missing: string[];
};

