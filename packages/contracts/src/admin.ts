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
  type: "DIRECT" | "GROUP";
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
  user_id: number;
  full_name: string;
  platform_role: string;
  is_active: boolean;
  platform_permissions: string[];
  modules: EffectiveModuleAccessOut[];
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

