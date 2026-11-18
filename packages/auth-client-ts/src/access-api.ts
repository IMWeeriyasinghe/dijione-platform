import type {
  AccessGrantIn,
  AccessMe,
  AccessPeople,
  AppointIn,
  ApplicationAdministrator,
  AppUser,
  AppUsers,
  RevokePreview,
} from "@dijione/contracts";

import { request } from "./http";

/** Delegated application access administration: every call goes to Platform Core through the
 * gateway (/api/access/{app}) with the caller's own session. Platform Core checks the caller's
 * appointment and authority on every request; nothing here is trusted for authorization. */
export function accessApi(moduleKey: string) {
  const base = `/api/access/${encodeURIComponent(moduleKey)}`;
  const json = (body: unknown): RequestInit => ({
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
  return {
    me: () => request<AccessMe>(`${base}/me`),
    users: () => request<AppUsers>(`${base}/users`),
    user: (userId: number) => request<AppUser>(`${base}/users/${userId}`),
    people: (q: string) => request<AccessPeople>(`${base}/people?q=${encodeURIComponent(q)}`),
    grant: (userId: number, body: AccessGrantIn) => request<AppUser>(`${base}/users/${userId}`, { method: "PUT", ...json(body) }),
    onboard: (entraObjectId: string, body: AccessGrantIn) =>
      request<AppUser>(`${base}/users/from-directory`, {
        method: "POST",
        ...json({ ...body, entra_object_id: entraObjectId }),
      }),
    revokePreview: (userId: number) => request<RevokePreview>(`${base}/users/${userId}/revoke-preview`),
    revoke: (userId: number, reason: string) =>
      request<AppUser>(`${base}/users/${userId}/revoke`, { method: "POST", ...json({ reason }) }),
    liftSuspension: (userId: number) => request<AppUser>(`${base}/users/${userId}/suspension`, { method: "DELETE" }),
    admins: () => request<ApplicationAdministrator[]>(`${base}/admins`),
    appoint: (userId: number, body: AppointIn) =>
      request<ApplicationAdministrator>(`${base}/admins/${userId}`, { method: "PUT", ...json(body) }),
    removeAdmin: (userId: number) => request<{ status: string }>(`${base}/admins/${userId}`, { method: "DELETE" }),
  };
}

export type AccessApi = ReturnType<typeof accessApi>;

/** The permission that shows an application's Management → Access entry. */
export const accessManagePermission = (prefix: string) => `${prefix}.access.manage`;
