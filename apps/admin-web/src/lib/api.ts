import type {
  AdminDashboardOut,
  AdminModuleOut,
  AdminPermissionOut,
  AdminRoleOut,
  AdminUserOut,
  AuditLogOut,
  ClientScope,
  EffectiveAccessOut,
} from "@dijione/contracts";
import { qs, request } from "@dijione/auth-client";

export { ApiError } from "@dijione/auth-client";

// DijiOne Admin Center — proxied to admin-api via this app's next.config.ts
// rewrites (and, when reached through shell-web, via its gateway rewrites).
export const getAdminDashboard = () => request<AdminDashboardOut>("/api/admin/dashboard");
export const listAdminUsers = () => request<AdminUserOut[]>("/api/admin/users");
export const getAdminUser = (id: number) => request<AdminUserOut>(`/api/admin/users/${id}`);
export const getEffectiveAccess = (id: number) =>
  request<EffectiveAccessOut>(`/api/admin/users/${id}/effective-access`);
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
export const listAdminClients = () => request<{ id: number; name: string }[]>("/api/admin/clients");
export const listAdminModules = () => request<AdminModuleOut[]>("/api/admin/modules");
export const listAdminRoles = () => request<AdminRoleOut[]>("/api/admin/roles");
export const listAdminPermissions = () => request<AdminPermissionOut[]>("/api/admin/permissions");
export const listAdminAudit = (params: { entity_type?: string; limit?: number } = {}) =>
  request<AuditLogOut[]>(`/api/admin/audit${qs(params)}`);
