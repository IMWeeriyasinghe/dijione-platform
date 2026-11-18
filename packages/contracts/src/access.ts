// Delegated application access administration (Platform Core /api/access/{app} and the Central
// Admin appointment endpoints). Mirrors apps/platform-api/app/schemas/app_access.py.

export type AccessClient = { id: number; name: string };
export type AccessScope = { all_clients: boolean; clients: AccessClient[] };
export type AccessRole = { key: string; name: string; description?: string };

export type AccessMe = {
  module_key: string;
  module_name: string;
  is_admin: boolean;
  can_appoint_admins: boolean;
  supports_client_scope: boolean;
  grantable_roles: AccessRole[];
  client_authority: AccessScope | null;
  default_role_name: string | null;
};

export type AccessSourceType = "DIRECT" | "GROUP" | "BASELINE" | "APPOINTMENT";

export type AccessSource = {
  type: AccessSourceType;
  role: string;
  role_name: string;
  group_id: number | null;
  group_name: string | null;
  mandated: boolean;
  applies: boolean;
  scope: AccessScope | null;
};

export type AccessSuspension = {
  user_id: number;
  full_name: string;
  email: string;
  reason: string;
  suspended_by_name: string | null;
  suspended_at: string;
};

export type AppointmentInfo = {
  can_appoint_admins: boolean;
  grantable_roles: AccessRole[];
  client_authority: AccessScope | null;
  appointed_by_name: string | null;
  appointed_at: string;
};

export type AppUser = {
  user_id: number;
  full_name: string;
  email: string;
  title: string | null;
  is_active: boolean;
  eligible_employee: boolean;
  has_access: boolean;
  role: string | null;
  role_name: string | null;
  sources: AccessSource[];
  suspension: AccessSuspension | null;
  administrator: AppointmentInfo | null;
  manageable: boolean;
  managed_reason: string | null;
};

export type AppUsers = { users: AppUser[]; default_access_note: string | null };

export type AccessPerson = {
  user_id: number | null;
  entra_object_id: string | null;
  full_name: string;
  email: string;
  job_title: string | null;
  department: string | null;
  source: "DIJIONE" | "DIRECTORY";
  has_access: boolean;
  role_name: string | null;
  can_grant: boolean;
  reason: string | null;
};

export type AccessPeople = { people: AccessPerson[]; directory_available: boolean };

export type AccessClientScopeIn = { all_clients: boolean; client_ids: number[] };

export type AccessGrantIn = { role: string; client_scope?: AccessClientScopeIn };

export type RevokePreview = {
  allowed: boolean;
  reason: string | null;
  removes_direct: AccessSource | null;
  suspends: AccessSource[];
  keeps: AccessSource[];
};

export type ApplicationAdministrator = {
  user_id: number;
  full_name: string;
  email: string;
  can_appoint_admins: boolean;
  grantable_roles: AccessRole[];
  client_authority: AccessScope | null;
  appointed_by_name: string | null;
  appointed_at: string;
  eligible_employee: boolean;
};

export type AppointIn = {
  grantable_roles: string[];
  client_authority?: AccessClientScopeIn;
  can_appoint_admins?: boolean;
  break_glass_reason?: string;
};
