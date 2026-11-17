import type {
  AccessDiagnosticsOut,
  AccessGroupDetailOut,
  AccessGroupOut,
  AdminDashboardOut,
  AdminModuleOut,
  AdminPermissionOut,
  AdminRoleOut,
  AdminUserOut,
  ApplicationDetailOut,
  AuditLogOut,
  ClientScope,
  DirectoryUserOut,
  EffectiveAccessOut,
  EntraGroupOut,
} from "@dijione/contracts";
import { qs, request } from "@dijione/auth-client";

export { ApiError } from "@dijione/auth-client";

// DijiOne Admin Center — proxied to admin-api via this app's next.config.ts
// rewrites (and, when reached through shell-web, via its gateway rewrites).
export const getAdminDashboard = (signal?: AbortSignal) =>
  request<AdminDashboardOut>("/api/admin/dashboard", { signal });
export const listAdminUsers = () => request<AdminUserOut[]>("/api/admin/users");
export const createAdminUser = (payload: { email: string; full_name: string; title?: string }) =>
  request<AdminUserOut>("/api/admin/users", { method: "POST", body: JSON.stringify(payload) });
export const getAdminUser = (id: number) => request<AdminUserOut>(`/api/admin/users/${id}`);
// Entra directory (read only, server-side; bounded results).
export const searchDirectory = (q: string) =>
  request<DirectoryUserOut[]>(`/api/admin/directory/users${qs({ q })}`);
export const addUserFromDirectory = (entra_object_id: string) =>
  request<AdminUserOut>("/api/admin/users/from-directory", { method: "POST", body: JSON.stringify({ entra_object_id }) });
export const verifyUserWithDirectory = (id: number) =>
  request<AdminUserOut>(`/api/admin/users/${id}/verify-directory`, { method: "POST" });
export const getEntraGroups = (id: number) => request<EntraGroupOut[]>(`/api/admin/users/${id}/entra-groups`);
export const userPhotoPath = (id: number) => `/api/admin/users/${id}/photo`;
export const directoryPhotoPath = (objectId: string) => `/api/admin/directory/users/${objectId}/photo`;
export const getEffectiveAccess = (id: number) =>
  request<EffectiveAccessOut>(`/api/admin/users/${id}/effective-access`);
export const getAccessDiagnostics = (id: number) =>
  request<AccessDiagnosticsOut>(`/api/admin/users/${id}/access-diagnostics`);
export const updateUserStatus = (id: number, is_active: boolean) =>
  request<AdminUserOut>(`/api/admin/users/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ is_active }),
  });
export const updatePlatformRole = (id: number, platform_role: string) =>
  request<AdminUserOut>(`/api/admin/users/${id}/platform-role`, {
    method: "PATCH",
    body: JSON.stringify({ platform_role }),
  });
export const upsertModuleAssignment = (
  userId: number,
  moduleKey: string,
  payload: { role: string; enabled: boolean; client_scope?: ClientScope | { all_clients: boolean; client_ids: number[] } }
) =>
  request<AdminUserOut>(`/api/admin/users/${userId}/modules/${moduleKey}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
export const removeModuleAssignment = (userId: number, moduleKey: string) =>
  request<AdminUserOut>(`/api/admin/users/${userId}/modules/${moduleKey}`, { method: "DELETE" });
// Lifts an explicit exclusion from an application's default employee access.
export const restoreDefaultAccess = (userId: number, moduleKey: string) =>
  request<AdminUserOut>(`/api/admin/users/${userId}/modules/${moduleKey}/restore-default`, { method: "POST" });
export const listAdminClients = () => request<{ id: number; name: string }[]>("/api/admin/clients");
export const listAdminModules = () => request<AdminModuleOut[]>("/api/admin/modules");
export const listAdminRoles = () => request<AdminRoleOut[]>("/api/admin/roles");
export const listAdminPermissions = () => request<AdminPermissionOut[]>("/api/admin/permissions");
export const listAdminAudit = (
  params: { entity_type?: string; entity_id?: number; user_id?: number; limit?: number } = {}
) =>
  request<AuditLogOut[]>(`/api/admin/audit${qs(params)}`);

// --- Access Groups (Phase 2.6) ---------------------------------------------
export const listAdminGroups = () => request<AccessGroupOut[]>("/api/admin/groups");
export const getAdminGroup = (id: number) => request<AccessGroupDetailOut>(`/api/admin/groups/${id}`);
export const createAdminGroup = (payload: {
  key: string;
  display_name: string;
  description?: string;
  group_type?: string;
}) =>
  request<AccessGroupDetailOut>("/api/admin/groups", {
    method: "POST",
    body: JSON.stringify(payload),
  });
export const updateAdminGroup = (
  id: number,
  payload: { display_name?: string; description?: string; group_type?: string }
) =>
  request<AccessGroupDetailOut>(`/api/admin/groups/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
export const setGroupStatus = (id: number, status: string) =>
  request<AccessGroupDetailOut>(`/api/admin/groups/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
export const addGroupMember = (id: number, userId: number) =>
  request<AccessGroupDetailOut>(`/api/admin/groups/${id}/members`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
export const removeGroupMember = (id: number, userId: number) =>
  request<AccessGroupDetailOut>(`/api/admin/groups/${id}/members/${userId}`, { method: "DELETE" });
export const upsertGroupModuleAssignment = (
  id: number,
  moduleKey: string,
  payload: { role: string; enabled: boolean; client_scope?: ClientScope | { all_clients: boolean; client_ids: number[] } }
) =>
  request<AccessGroupDetailOut>(`/api/admin/groups/${id}/modules/${moduleKey}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
export const removeGroupModuleAssignment = (id: number, moduleKey: string) =>
  request<AccessGroupDetailOut>(`/api/admin/groups/${id}/modules/${moduleKey}`, { method: "DELETE" });

// --- Application-centric admin (Phase 2.6) ---------------------------------
export const getApplicationDetail = (moduleKey: string) =>
  request<ApplicationDetailOut>(`/api/admin/applications/${moduleKey}`);
