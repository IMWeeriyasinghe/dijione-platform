import type { NotificationOut } from "@dijione/contracts";
import { qs, request } from "./http";

// Platform Core's notification surface — used by the shared
// NotificationsPanel shell component in every app.
export const listNotifications = (unreadOnly = false) =>
  request<NotificationOut[]>(`/api/notifications${qs({ unread_only: unreadOnly })}`);
export const markNotificationRead = (id: number) =>
  request<{ status: string }>(`/api/notifications/${id}/read`, { method: "POST" });
