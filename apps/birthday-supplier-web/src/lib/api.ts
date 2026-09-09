import type {
  OrderIssueOut,
  OrderIssueType,
  OrderTimelineResponse,
  SupplierOrderListResponse,
  SupplierOrderView,
} from "@dijione/contracts";

/** This module only ever calls `/api/birthday/portal/*` (plus the dev-only
 * login endpoints) — never `/api/birthday/orders` or `/api/birthday/suppliers`
 * (internal-only paths). That boundary is enforced by convention: there is
 * no other API client file in this app. */

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function qs(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&");
}

async function request<T>(path: string, token: string | null, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// --- Supplier auth mode (drives which sign-in UI to render) -----------
export type SupplierAuthMode = "dev" | "entra";

export const getSupplierAuthConfig = () =>
  request<{ supplier_auth_mode: SupplierAuthMode }>(
    "/api/birthday/supplier/auth/config",
    null,
  );

// --- Dev-only persona auth (see lib/supplier-auth.tsx) -----------------
export type DevSupplierPersona = {
  supplier_user_id: number;
  supplier_id: number;
  email: string;
  full_name: string;
  supplier_name: string;
};

export const listDevSupplierPersonas = () =>
  request<DevSupplierPersona[]>("/api/birthday/internal/dev/supplier-users", null);

export const devSupplierLogin = (supplier_user_id: number) =>
  request<{ access_token: string }>("/api/birthday/internal/dev/supplier-login", null, {
    method: "POST",
    body: JSON.stringify({ supplier_user_id }),
  });

// --- Supplier portal ------------------------------------------------
export const listPortalOrders = (
  token: string,
  params: { search?: string; sort_by?: string; sort_direction?: string; page?: number; page_size?: number } = {}
) => request<SupplierOrderListResponse>(`/api/birthday/portal/orders${qs(params)}`, token);

export const getPortalOrder = (token: string, id: number) =>
  request<SupplierOrderView>(`/api/birthday/portal/orders/${id}`, token);

// Merged acknowledge+confirm (plan §O) — one commitment, one click.
export const acceptPortalOrder = (token: string, id: number) =>
  request<SupplierOrderView>(`/api/birthday/portal/orders/${id}/accept`, token, { method: "POST" });

export const updatePortalOrderStatus = (token: string, id: number, status: string) =>
  request<SupplierOrderView>(`/api/birthday/portal/orders/${id}/status`, token, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });

// Typed problem report (plan §O/§U) — replaces the old free-text-only
// /issue endpoint with a structured, resolvable record.
export const raisePortalIssue = (token: string, id: number, type: OrderIssueType, detail: string) =>
  request<OrderIssueOut>(`/api/birthday/portal/orders/${id}/issues`, token, {
    method: "POST",
    body: JSON.stringify({ type, detail }),
  });

export const listPortalOrderIssues = (token: string, id: number) =>
  request<OrderIssueOut[]>(`/api/birthday/portal/orders/${id}/issues`, token);

// Unified Timeline (§G), supplier-filtered — the conversation + lifecycle.
export const getPortalOrderTimeline = (token: string, id: number) =>
  request<OrderTimelineResponse>(`/api/birthday/portal/orders/${id}/timeline`, token);

// Flow 1 (§G): the supplier posts a Portal message on this order. Plain
// conversation — it does NOT create an issue or change status.
export const postPortalOrderMessage = (
  token: string,
  id: number,
  body: string,
  issue_id?: number | null,
) =>
  request<OrderTimelineResponse>(`/api/birthday/portal/orders/${id}/messages`, token, {
    method: "POST",
    body: JSON.stringify({ body, issue_id: issue_id ?? null }),
  });

export type SupplierDashboardSummary = {
  new_orders: number;
  due_today: number;
  due_tomorrow: number;
  overdue: number;
  out_for_delivery: number;
  open_issues: number;
  completed_today: number;
};

export const getPortalDashboard = (token: string) =>
  request<SupplierDashboardSummary>("/api/birthday/portal/dashboard", token);
