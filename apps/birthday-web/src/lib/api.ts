import type {
  AddressVerificationUpdateInput,
  BirthdayDashboardSummary,
  BirthdayOrderCreateInput,
  BirthdayOrderListResponse,
  BirthdayOrderOut,
  BirthdayOrderUpdateInput,
  BirthdaySummaryOut,
  BirthdayUpcomingResponse,
  ConfirmReleaseInput,
  DeliveryAddressUpdateInput,
  OrderIssueCreateInput,
  OrderIssueOut,
  ReadinessCheckResponse,
  SpecialRequirementCreateInput,
  SpecialRequirementOut,
  SupplierCatalogueItemCreateInput,
  SupplierCatalogueItemOut,
  SupplierCatalogueItemUpdateInput,
  SupplierCreateInput,
  SupplierListResponse,
  SupplierLocationCreateInput,
  SupplierLocationOut,
  SupplierOut,
  SupplierUpdateInput,
  SupplierUserCreateInput,
  SupplierUserOut,
  SupplierUserUpdateInput,
  UpcomingBirthdaysResponse,
  VerifyAddressInput,
  VerifyAddressResponse,
} from "@dijione/contracts";
import { qs, request } from "@dijione/auth-client";

export { ApiError } from "@dijione/auth-client";

// --- Dashboard -------------------------------------------------
export const getDashboardSummary = () => request<BirthdayDashboardSummary>("/api/birthday/dashboard");
export const getSummary = () => request<BirthdaySummaryOut>("/api/birthday/summary");
export const getUpcoming = (daysAhead?: number) =>
  request<BirthdayUpcomingResponse>(`/api/birthday/upcoming${qs({ days_ahead: daysAhead })}`);

// Live-BambooHR-driven employee-birthday directory (distinct from
// getUpcoming above, which only lists already-detected/ordered
// BirthdayOrder rows). Powers the Upcoming Birthdays page.
export const getUpcomingBirthdays = (params: {
  days?: number;
  search?: string;
  filter?: string;
  province?: string;
  sort_by?: string;
  sort_direction?: string;
  page?: number;
  page_size?: number;
} = {}) => request<UpcomingBirthdaysResponse>(`/api/birthday/employees/upcoming-birthdays${qs(params)}`);

// --- Orders -------------------------------------------------
export const listOrders = (params: {
  search?: string;
  status_filter?: string;
  lead_time_class?: string;
  office_location?: string;
  supplier_id?: number;
  address_verification_status?: string;
  sort_by?: string;
  sort_direction?: string;
  page?: number;
  page_size?: number;
} = {}) => request<BirthdayOrderListResponse>(`/api/birthday/orders${qs(params)}`);

export const getOrder = (id: number) => request<BirthdayOrderOut>(`/api/birthday/orders/${id}`);

export const createOrder = (payload: BirthdayOrderCreateInput) =>
  request<BirthdayOrderOut>("/api/birthday/orders", { method: "POST", body: JSON.stringify(payload) });

export const updateOrder = (id: number, payload: BirthdayOrderUpdateInput) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const holdOrder = (id: number, hold_reason: string) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/hold`, {
    method: "POST",
    body: JSON.stringify({ hold_reason }),
  });

export const releaseOrder = (id: number, note?: string) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/release`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });

export const cancelOrder = (id: number, reason?: string) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export const addSpecialRequirement = (id: number, payload: SpecialRequirementCreateInput) =>
  request<SpecialRequirementOut>(`/api/birthday/orders/${id}/special-requirements`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const updateAddressVerification = (id: number, payload: AddressVerificationUpdateInput) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/address-verification`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const updateDeliveryAddress = (id: number, payload: DeliveryAddressUpdateInput) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/delivery-address`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const sendOrderToSupplier = (id: number) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/send-to-supplier`, { method: "POST" });

export const resendOrderToSupplier = (id: number) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/resend`, { method: "POST" });

export const deleteOrder = (id: number) =>
  request<void>(`/api/birthday/orders/${id}`, { method: "DELETE" });

export const getOrderReadiness = (id: number) =>
  request<ReadinessCheckResponse>(`/api/birthday/orders/${id}/readiness`);

// "Verification is the approval" (plan §K) — the one routine human
// checkpoint. Auto-releases a standard order; flags a non-standard one
// into REQUIRES_REVIEW for confirmRelease below.
export const verifyAddress = (id: number, payload: VerifyAddressInput = {}) =>
  request<VerifyAddressResponse>(`/api/birthday/orders/${id}/verify`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const confirmRelease = (id: number, payload: ConfirmReleaseInput = {}) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/confirm-release`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const listOrderIssues = (id: number) =>
  request<OrderIssueOut[]>(`/api/birthday/orders/${id}/issues`);

export const raiseOrderIssue = (id: number, payload: OrderIssueCreateInput) =>
  request<OrderIssueOut>(`/api/birthday/orders/${id}/issues`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const resolveOrderIssue = (id: number, issueId: number, resolution_detail: string) =>
  request<OrderIssueOut>(`/api/birthday/orders/${id}/issues/${issueId}/resolve`, {
    method: "PATCH",
    body: JSON.stringify({ resolution_detail }),
  });

// --- Suppliers -------------------------------------------------
export const listSuppliers = (params: {
  search?: string;
  status_filter?: string;
  sort_by?: string;
  sort_direction?: string;
  page?: number;
  page_size?: number;
} = {}) => request<SupplierListResponse>(`/api/birthday/suppliers${qs(params)}`);

export const getSupplier = (id: number) => request<SupplierOut>(`/api/birthday/suppliers/${id}`);

export const createSupplier = (payload: SupplierCreateInput) =>
  request<SupplierOut>("/api/birthday/suppliers", { method: "POST", body: JSON.stringify(payload) });

export const updateSupplier = (id: number, payload: SupplierUpdateInput) =>
  request<SupplierOut>(`/api/birthday/suppliers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const listSupplierLocations = (supplierId: number) =>
  request<SupplierLocationOut[]>(`/api/birthday/suppliers/${supplierId}/locations`);

export const addSupplierLocation = (supplierId: number, payload: SupplierLocationCreateInput) =>
  request<SupplierLocationOut>(`/api/birthday/suppliers/${supplierId}/locations`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const listSupplierCatalogue = (supplierId: number) =>
  request<SupplierCatalogueItemOut[]>(`/api/birthday/suppliers/${supplierId}/catalogue`);

export const addSupplierCatalogueItem = (supplierId: number, payload: SupplierCatalogueItemCreateInput) =>
  request<SupplierCatalogueItemOut>(`/api/birthday/suppliers/${supplierId}/catalogue`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const updateSupplierCatalogueItem = (
  supplierId: number,
  itemId: number,
  payload: SupplierCatalogueItemUpdateInput
) =>
  request<SupplierCatalogueItemOut>(`/api/birthday/suppliers/${supplierId}/catalogue/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

// --- Supplier Users -------------------------------------------------
export const listSupplierUsers = (supplierId: number) =>
  request<SupplierUserOut[]>(`/api/birthday/suppliers/${supplierId}/users`);

export const createSupplierUser = (supplierId: number, payload: SupplierUserCreateInput) =>
  request<SupplierUserOut>(`/api/birthday/suppliers/${supplierId}/users`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const updateSupplierUser = (supplierId: number, userId: number, payload: SupplierUserUpdateInput) =>
  request<SupplierUserOut>(`/api/birthday/suppliers/${supplierId}/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

// --- Admin -------------------------------------------------
// Calls the same detection service the production external scheduler
// triggers — for UAT/ops use, never a separate/duplicated detection path.
export type RunDetectionResult = {
  run_id: string;
  employees_scanned: number;
  orders_created: number;
  orders_existing: number;
  exceptions: number;
  ineligible_skipped: number;
  errors: Array<{ employee_id: string | null; error: string }>;
};

export const runBirthdayDetection = () =>
  request<RunDetectionResult>("/api/birthday/admin/run-detection", { method: "POST" });

export type ScanRunOut = {
  run_id: string;
  trigger: string;
  started_at: string | null;
  finished_at: string | null;
  employees_scanned: number;
  orders_created: number;
  orders_existing: number;
  exceptions: number;
  ineligible_skipped: number;
  errors: Array<{ employee_id: string | null; error: string }>;
};

export const listScanRuns = (limit?: number) =>
  request<ScanRunOut[]>(`/api/birthday/admin/scan-runs${qs({ limit })}`);

// --- Config -------------------------------------------------
export type DetectionConfig = {
  id: number;
  normal_threshold_days: number;
  short_notice_threshold_days: number;
  urgent_threshold_days: number;
  window_lookback_days: number;
  window_lookahead_days: number;
  default_quantity: number;
  verify_buffer_days: number;
  acknowledgement_sla_hours: number;
  auto_release_enabled: boolean;
  updated_by: number | null;
};

export const getConfig = () => request<DetectionConfig>("/api/birthday/config");

export const updateConfig = (payload: Partial<DetectionConfig>) =>
  request<DetectionConfig>("/api/birthday/config", { method: "PATCH", body: JSON.stringify(payload) });
