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
  AccessSuspension,
  ApplicationAdministrator,
  AppointIn,
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

// Delegated application access: administrators (Super Admin), suspensions, registry switch.
const breakGlass = (reason?: string) => (reason ? `?break_glass_reason=${encodeURIComponent(reason)}` : "");
export const listApplicationAdministrators = (moduleKey: string) =>
  request<ApplicationAdministrator[]>(`/api/admin/applications/${moduleKey}/administrators`);
export const appointApplicationAdministrator = (moduleKey: string, userId: number, payload: AppointIn) =>
  request<ApplicationAdministrator>(`/api/admin/applications/${moduleKey}/administrators/${userId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
export const removeApplicationAdministrator = (moduleKey: string, userId: number, reason?: string) =>
  request<{ status: string }>(`/api/admin/applications/${moduleKey}/administrators/${userId}${breakGlass(reason)}`, {
    method: "DELETE",
  });
export const listApplicationSuspensions = (moduleKey: string) =>
  request<AccessSuspension[]>(`/api/admin/applications/${moduleKey}/suspensions`);
export const liftApplicationSuspension = (moduleKey: string, userId: number) =>
  request<{ status: string }>(`/api/admin/applications/${moduleKey}/suspensions/${userId}`, { method: "DELETE" });
export const setModuleEnabled = (moduleKey: string, enabled: boolean) =>
  request<AdminModuleOut>(`/api/admin/modules/${moduleKey}`, { method: "PATCH", body: JSON.stringify({ enabled }) });

// --- Notifications (email outbox; owned by Platform Core, proxied by admin-api) ---------------
export type EmailStatus =
  | "PENDING" | "SENDING" | "RETRY" | "SUBMITTED" | "SIMULATED" | "FAILED"
  | "BLOCKED" | "DISABLED" | "SUPERSEDED" | "SKIPPED";

export interface EmailOutboxItem {
  id: number;
  correlation_id: string;
  application_key: string;
  application_name: string;
  event_type: string;
  recipient_email: string;
  recipient_user_id: number | null;
  subject: string;
  status: EmailStatus;
  attempts: number;
  max_attempts: number;
  transport_outcome: string | null;
  created_at: string;
  not_before: string;
  last_attempt_at: string | null;
  completed_at: string | null;
  can_retry: boolean;
  // detail only
  last_error?: string | null;
  graph_request_id?: string | null;
  superseded_by_id?: number | null;
  template_data?: Record<string, unknown>;
}

export interface EmailOutboxPage {
  total: number;
  items: EmailOutboxItem[];
}

export interface NotificationSummary {
  counts: Record<EmailStatus, number>;
  environment: string;
  transport: "null" | "graph";
  configured_policy: string;
  effective_policy: "simulated" | "internal_allowlist" | "production" | "disabled";
  is_production: boolean;
  sender_mailbox: string | null;
  access_notifications_enabled: boolean;
  dispatcher_enabled: boolean;
  applications: { key: string; name: string }[];
  statuses: EmailStatus[];
}

export interface NotificationEvent {
  event_type: string;
  application_key: string;
  subject: string;
  description: string;
  enabled: boolean;
}

export interface EmailTestRecipient {
  id: number;
  address: string;
  label: string;
  active: boolean;
  created_at: string;
}

export interface OutboxFilters {
  application?: string;
  event_type?: string;
  recipient?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export const getNotificationSummary = () => request<NotificationSummary>("/api/admin/notifications/summary");
export const listEmailOutbox = (filters: OutboxFilters) =>
  request<EmailOutboxPage>(`/api/admin/notifications/outbox${qs(filters as Record<string, string | number | undefined>)}`);
export const getEmailOutboxItem = (id: number) => request<EmailOutboxItem>(`/api/admin/notifications/outbox/${id}`);
export const retryEmailOutboxItem = (id: number) =>
  request<EmailOutboxItem>(`/api/admin/notifications/outbox/${id}/retry`, { method: "POST" });
export const dispatchNotificationsNow = () =>
  request<{ processed: Record<string, number> }>("/api/admin/notifications/dispatch", { method: "POST" });
export const listNotificationEvents = () => request<NotificationEvent[]>("/api/admin/notifications/events");
export const setNotificationEvent = (eventType: string, enabled: boolean) =>
  request<NotificationEvent[]>(`/api/admin/notifications/events/${encodeURIComponent(eventType)}`, {
    method: "PUT",
    body: JSON.stringify({ enabled }),
  });
export const listEmailTestRecipients = () => request<EmailTestRecipient[]>("/api/admin/notifications/test-recipients");
export const addEmailTestRecipient = (address: string, label: string) =>
  request<EmailTestRecipient[]>("/api/admin/notifications/test-recipients", {
    method: "POST",
    body: JSON.stringify({ address, label }),
  });
export const removeEmailTestRecipient = (id: number) =>
  request<EmailTestRecipient[]>(`/api/admin/notifications/test-recipients/${id}`, { method: "DELETE" });
