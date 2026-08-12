from datetime import datetime

from pydantic import BaseModel


class ClientScopeOut(BaseModel):
    all_clients: bool
    client_ids: list[int] = []
    client_names: list[str] = []


class ClientScopeIn(BaseModel):
    all_clients: bool = False
    client_ids: list[int] = []


class ModuleAssignmentOut(BaseModel):
    module_key: str
    module_name: str
    role: str
    role_name: str
    enabled: bool
    client_scope: ClientScopeOut | None = None


class ModuleAssignmentIn(BaseModel):
    role: str
    enabled: bool = True
    client_scope: ClientScopeIn | None = None


class AdminUserOut(BaseModel):
    id: int
    email: str
    full_name: str
    title: str | None
    platform_role: str
    is_active: bool
    identity_provider: str
    entra_object_id: str | None
    last_login_at: datetime | None
    created_at: datetime
    module_assignments: list[ModuleAssignmentOut]


class UpdateUserStatusIn(BaseModel):
    is_active: bool


class UpdatePlatformRoleIn(BaseModel):
    platform_role: str


class AdminModuleOut(BaseModel):
    id: int
    key: str
    name: str
    description: str
    icon: str
    route: str
    status: str
    enabled: bool
    display_order: int
    user_count: int


class AdminRoleOut(BaseModel):
    id: int
    module_key: str | None
    key: str
    name: str
    description: str
    is_system: bool
    permission_count: int
    user_count: int


class AdminPermissionOut(BaseModel):
    id: int
    key: str
    name: str
    description: str
    module_key: str | None
    category: str


class AuditLogOut(BaseModel):
    id: int
    actor_id: int | None
    actor_name: str | None
    action: str
    entity_type: str
    entity_id: int
    previous_state: str
    new_state: str
    metadata: str
    created_at: datetime


class EffectiveModuleAccessOut(BaseModel):
    module_key: str
    module_name: str
    enabled: bool
    role: str
    role_name: str
    client_scope: ClientScopeOut
    permissions: list[str]


class EffectiveAccessOut(BaseModel):
    user_id: int
    full_name: str
    platform_role: str
    is_active: bool
    platform_permissions: list[str]
    modules: list[EffectiveModuleAccessOut]


class AdminDashboardOut(BaseModel):
    total_users: int
    active_users: int
    platform_admins: int
    super_admins: int
    active_modules: int
    pending_talent_requests: int
