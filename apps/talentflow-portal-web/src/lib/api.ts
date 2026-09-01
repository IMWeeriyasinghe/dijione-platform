import type {
  ClientDashboardOut,
  ClientInterviewOut,
  ClientSafeCandidateOut,
  TalentRequestOut,
} from "@dijione/contracts";

import { currentSession, refreshSessionFromStoredToken } from "./external-auth";

/** This module only ever calls `/api/talent/external/*` — the redeem
 * endpoint and the client-safe read routes. It has no function that calls
 * any internal `/api/talent/*` path; that boundary is the whole point of
 * this app being separate. */

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function qs(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== "",
  );
  if (entries.length === 0) return "";
  return (
    "?" +
    entries
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
      .join("&")
  );
}

function rawRequest(path: string, session: string | null): Promise<Response> {
  return fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(session ? { Authorization: `Bearer ${session}` } : {}),
    },
  });
}

async function request<T>(path: string): Promise<T> {
  let res = await rawRequest(path, currentSession());

  // One silent re-redeem on 401 — the ≈45-min session JWT has likely just
  // expired while the grant is still valid. If re-redeem also fails, the
  // grant is gone (revoked/expired) and the session is over.
  if (res.status === 401) {
    const fresh = await refreshSessionFromStoredToken();
    if (fresh) res = await rawRequest(path, fresh);
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const getDashboard = () =>
  request<ClientDashboardOut>("/api/talent/external/dashboard");

export const listRequests = (
  params: { search?: string; stage?: string; status_filter?: string } = {},
) => request<TalentRequestOut[]>(`/api/talent/external/requests${qs(params)}`);

export const getRequest = (id: number) =>
  request<TalentRequestOut>(`/api/talent/external/requests/${id}`);

export const listRequestCandidates = (id: number) =>
  request<ClientSafeCandidateOut[]>(`/api/talent/external/requests/${id}/candidates`);

export const listInterviews = () =>
  request<ClientInterviewOut[]>("/api/talent/external/interviews");
