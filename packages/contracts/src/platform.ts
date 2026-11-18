// Platform Core contracts — users, roles, module registry, notifications.
// Mirrors apps/platform-api/app/schemas/*.py — kept in sync by hand for the
// MVP. If/when the API surface grows, consider generating these from the
// FastAPI OpenAPI schema instead.
// Published contract: a breaking change to a shape here needs a version bump
// (packages/contracts's own package.json), since every *-web app imports it.

export type ModuleRole = {
  module_key: string;
  role: string;
  client_id: number | null;
  enabled?: boolean;
  /** The permissions this application entry carries (as the session token does). Shells use it
   * to show navigation such as Management → Access; the APIs enforce. */
  permissions?: string[];
};

export type CurrentUser = {
  id: number;
  email: string;
  full_name: string;
  title: string | null;
  platform_role: "PLATFORM_USER" | "PLATFORM_ADMIN" | "SUPER_ADMIN";
  avatar_color: string | null;
  module_roles: ModuleRole[];
  platform_permissions: string[];
  /** Present only while a read-only View-as token is in use. */
  view_as?: ViewAsInfo | null;
};

export type ViewAsInfo = {
  session_id: string;
  expires_at: string;
  actor_id: number;
  actor_name: string;
  read_only: boolean;
};

export type ViewAsStartOut = {
  access_token: string;
  session_id: string;
  expires_at: string;
  target: { id: number; full_name: string; email: string; title: string | null };
};

export type DevPersona = {
  persona_key: string;
  full_name: string;
  title: string | null;
  platform_role: string;
  module_roles: ModuleRole[];
  avatar_color: string | null;
};

export type ModuleOut = {
  id: number;
  key: string;
  name: string;
  description: string;
  icon: string;
  route: string;
  status: string;
  enabled: boolean;
  display_order: number;
};

export type NotificationOut = {
  id: number;
  type: string;
  title: string;
  body: string;
  is_read: boolean;
  related_entity_type: string | null;
  related_entity_id: number | null;
  link_url?: string | null;
  created_at: string;
};

