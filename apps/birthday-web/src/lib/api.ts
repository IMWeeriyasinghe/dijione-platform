import type {
  AddressVerificationUpdateInput,
  BirthdayDashboardSummary,
  BirthdayOrderCreateInput,
  BirthdayOrderListResponse,
  BirthdayOrderOut,
  BirthdayOrderUpdateInput,
  BirthdaySummaryOut,
  BirthdayUpcomingResponse,
  ReadinessCheckResponse,
  RejectRequestInput,
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

export const sendOrderToSupplier = (id: number) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/send-to-supplier`, { method: "POST" });

export const resendOrderToSupplier = (id: number) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/resend`, { method: "POST" });

export const deleteOrder = (id: number) =>
  request<void>(`/api/birthday/orders/${id}`, { method: "DELETE" });

export const getOrderReadiness = (id: number) =>
  request<ReadinessCheckResponse>(`/api/birthday/orders/${id}/readiness`);

export const submitForApproval = (id: number) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/submit-for-approval`, { method: "POST" });

export const approveOrder = (id: number) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/approve`, { method: "POST" });

export const rejectOrder = (id: number, payload: RejectRequestInput) =>
  request<BirthdayOrderOut>(`/api/birthday/orders/${id}/reject`, {
    method: "POST",
    body: JSON.stringify(payload),
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
