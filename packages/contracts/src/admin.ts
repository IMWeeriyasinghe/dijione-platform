// admin
// DijiOne Admin Center. Mirrors apps/platform-api/app/schemas/admin.py.
// Published contract: a breaking change to a shape here needs a version bump
// (packages/contracts's own package.json), since every *-web app imports it.

// --- DijiOne Admin Center (Phase 2) ----------------------------------------
// Mirrors apps/api/app/schemas/admin.py.

export type ClientScope = {
  all_clients: boolean;
  client_ids: number[];
  client_names: string[];
};

export type ModuleAssignmentOut = {
  module_key: string;
  module_name: string;
  role: string;
  role_name: string;
  enabled: boolean;
  client_scope: ClientScope | null;
};

export type AdminUserOut = {
  id: number;
  email: string;
  full_name: string;
  title: string | null;
  platform_role: string;
  is_active: boolean;
  identity_provider: string;
  entra_object_id: string | null;
  last_login_at: string | null;
  created_at: string;
  module_assignments: ModuleAssignmentOut[];
};

export type AdminModuleOut = {
  id: number;
  key: string;
  name: string;
  description: string;
  icon: string;
  route: string;
  status: string;
  enabled: boolean;
  display_order: number;
  user_count: number;
  /** Whether the module's authorization reads client scope (Admin Center shows Client Scope only then). */
  supports_client_scope?: boolean;
};

export type AdminRoleOut = {
  id: number;
  module_key: string | null;
  key: string;
  name: string;
  description: string;
  is_system: boolean;
  permission_count: number;
  user_count: number;
};

export type AdminPermissionOut = {
  id: number;
  key: string;
  name: string;
  description: string;
  module_key: string | null;
  category: string;
};

export type AuditLogOut = {
  id: number;
  actor_id: number | null;
  actor_name: string | null;
  action: string;
  entity_type: string;
  entity_id: number;
  previous_state: string;
  new_state: string;
  metadata: string;
  created_at: string;
};

export type AccessSourceOut = {
  type: "DIRECT" | "GROUP" | "BASELINE";
  role: string | null;
  group_id: number | null;
  group_name: string | null;
};

export type EffectiveModuleAccessOut = {
  module_key: string;
  module_name: string;
  enabled: boolean;
  role: string;
  role_name: string;
  client_scope: ClientScope;
  permissions: string[];
  sources: AccessSourceOut[];
};

export type EffectiveAccessOut = {
  default_access_excluded?: string[];
  user_id: number;
  full_name: string;
  platform_role: string;
  is_active: boolean;
  platform_permissions: string[];
  modules: EffectiveModuleAccessOut[];
};

export type DiagSource = {
  type: "DIRECT" | "GROUP" | "DEFAULT";
  role: string;
  group_name: string | null;
  permissions: string[];
  client_scope: string;
};

export type DiagModule = {
  module_key: string;
  module_name: string;
  has_access: boolean;
  role: string;
  role_name: string;
  permissions: string[];
  sources: DiagSource[];
  client_scope: ClientScope;
  uses_client_scope: boolean;
  scope_explanation: string;
  inactive: { type: string; role: string; group_name: string | null; reason: string }[];
};

export type AccessDiagnosticsOut = {
  user_id: number;
  full_name: string;
  email: string;
  account: {
    is_active: boolean;
    identity_provider: string;
    entra_linked: boolean;
    internal_employee: boolean;
    platform_role: string;
    platform_permissions: string[];
    last_sign_in_at: string | null;
    created_at: string | null;
  };
  default_access: {
    module_key: string;
    module_name: string;
    role: string;
    state: "GRANTED" | "EXCLUDED" | "NOT_ELIGIBLE" | "MODULE_DISABLED";
    reasons: string[];
  }[];
  groups: {
    group_id: number;
    group_name: string;
    status: string;
    grants: { module_key: string; role: string; enabled: boolean }[];
  }[];
  modules: DiagModule[];
  session: {
    last_sign_in_at: string | null;
    token_issue_time_available: boolean;
    token_issue_time_note: string;
    access_changes_since_last_sign_in: number | null;
    latest_access_change_at: string | null;
    token_lifetime_minutes: number;
  };
  checks: { key: string; level: "ok" | "info" | "warning"; message: string }[];
};

export type GroupMemberOut = {
  user_id: number;
  email: string;
  full_name: string;
};

export type GroupModuleAssignmentOut = {
  module_key: string;
  module_name: string;
  role: string;
  role_name: string;
  enabled: boolean;
  client_scope: ClientScope | null;
};

export type AccessGroupOut = {
  id: number;
  key: string;
  display_name: string;
  description: string;
  status: string;
  group_type: string;
  member_count: number;
  module_count: number;
  created_at: string;
  updated_at: string;
};

export type AccessGroupDetailOut = {
  id: number;
  key: string;
  display_name: string;
  description: string;
  status: string;
  group_type: string;
  created_at: string;
  updated_at: string;
  members: GroupMemberOut[];
  module_assignments: GroupModuleAssignmentOut[];
};

export type ApplicationAssignedUserOut = {
  user_id: number;
  email: string;
  full_name: string;
  role: string;
  role_name: string;
  enabled: boolean;
  client_scope: ClientScope;
};

export type ApplicationAssignedGroupOut = {
  group_id: number;
  group_key: string;
  group_name: string;
  role: string;
  role_name: string;
  enabled: boolean;
  client_scope: ClientScope;
};

export type ApplicationDetailOut = {
  module_key: string;
  module_name: string;
  description: string;
  status: string;
  enabled: boolean;
  assigned_users: ApplicationAssignedUserOut[];
  assigned_groups: ApplicationAssignedGroupOut[];
  direct_user_count: number;
  group_count: number;
  supports_client_scope?: boolean;
};

export type AdminDashboardOut = {
  total_users: number;
  active_users: number;
  platform_admins: number;
  super_admins: number;
  active_modules: number;
  pending_talent_requests: number;
};

export const PLATFORM_ROLE_LABELS: Record<string, string> = {
  SUPER_ADMIN: "Super Admin",
  PLATFORM_ADMIN: "Platform Admin",
  PLATFORM_USER: "Platform User",
};

