import type {
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

export const acknowledgePortalOrder = (token: string, id: number) =>
  request<SupplierOrderView>(`/api/birthday/portal/orders/${id}/acknowledge`, token, { method: "POST" });

export const updatePortalOrderStatus = (token: string, id: number, status: string) =>
  request<SupplierOrderView>(`/api/birthday/portal/orders/${id}/status`, token, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });

export const raisePortalIssue = (token: string, id: number, detail: string) =>
  request<SupplierOrderView>(`/api/birthday/portal/orders/${id}/issue`, token, {
    method: "POST",
    body: JSON.stringify({ detail }),
  });
