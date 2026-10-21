import { getToken, request } from "@dijione/auth-client";
import type { Freshness, IdentityReport, OnsiteSite, SiteHealth, SyncAccepted, SyncRun } from "./types";

export { ApiError } from "@dijione/auth-client";

// Every call goes to this module's own API (/api/onsite/*) — never another
// application module's endpoints (guarded by src/__tests__/boundaries.test.ts).
export const ONSITE_API = "/api/onsite";

export const getFreshness = () => request<Freshness>(`${ONSITE_API}/freshness`);
export const getHealth = () => request<SiteHealth>(`${ONSITE_API}/admin/health`);
export const getSyncHistory = () => request<SyncRun[]>(`${ONSITE_API}/sync/history?limit=10`);
export const getSyncRun = (runId: string) => request<SyncRun>(`${ONSITE_API}/sync/runs/${encodeURIComponent(runId)}`);
export const requestSync = () => request<SyncAccepted>(`${ONSITE_API}/sync`, { method: "POST" });

export const getSites = () => request<OnsiteSite[]>(`${ONSITE_API}/admin/sites`);
export const setSiteEnabled = (siteId: string, enabled: boolean) =>
  request<OnsiteSite>(`${ONSITE_API}/admin/sites/${encodeURIComponent(siteId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });

export const getIdentityReport = () => request<IdentityReport>(`${ONSITE_API}/admin/identity-match`);

export const IDENTITY_CSV_PATH = `${ONSITE_API}/admin/identity-match?format=csv`;

/** Download the CSV with the caller's bearer token (a plain link would not send it). */
export async function downloadIdentityCsv(): Promise<void> {
  const token = getToken();
  const resp = await fetch(IDENTITY_CSV_PATH, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!resp.ok) throw new Error(`Export failed (${resp.status})`);
  const url = URL.createObjectURL(await resp.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = "onsite-identity-match.csv";
  a.click();
  URL.revokeObjectURL(url);
}
