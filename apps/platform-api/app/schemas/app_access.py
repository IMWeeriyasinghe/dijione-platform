"""Delegated application access administration (``/api/access/{app}`` and the Central Admin
appointment / suspension endpoints)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.admin import ClientScopeIn


class AccessClientOut(BaseModel):
    id: int  # platform Client.id, as Central Admin's client picker uses
    name: str


class AccessScopeOut(BaseModel):
    all_clients: bool
    clients: list[AccessClientOut] = []


class AccessRoleOut(BaseModel):
    key: str
    name: str
    description: str = ""


class AccessMeOut(BaseModel):
    module_key: str
    module_name: str
    is_admin: bool
    can_appoint_admins: bool = False
    supports_client_scope: bool = False
    grantable_roles: list[AccessRoleOut] = []
    client_authority: AccessScopeOut | None = None  # clients this administrator may grant (scoped apps)
    default_role_name: str | None = None  # access every eligible employee has (e.g. DijiAtWork)


class AccessSourceOut(BaseModel):
    type: str  # DIRECT / GROUP / BASELINE / APPOINTMENT
    role: str
    role_name: str
    group_id: int | None = None
    group_name: str | None = None
    mandated: bool = False  # default access or a SYSTEM group: cannot be removed or suspended
    applies: bool = True  # False while suspended
    scope: AccessScopeOut | None = None


class SuspensionOut(BaseModel):
    user_id: int
    full_name: str
    email: str
    reason: str
    suspended_by_name: str | None = None
    suspended_at: datetime


class AppointmentInfoOut(BaseModel):
    can_appoint_admins: bool
    grantable_roles: list[AccessRoleOut]
    client_authority: AccessScopeOut | None = None
    appointed_by_name: str | None = None
    appointed_at: datetime


class AppUserOut(BaseModel):
    user_id: int
    full_name: str
    email: str
    title: str | None = None
    is_active: bool
    eligible_employee: bool
    has_access: bool
    role: str | None = None  # the effective (primary) role, as the session carries it
    role_name: str | None = None
    sources: list[AccessSourceOut] = []
    suspension: SuspensionOut | None = None
    administrator: AppointmentInfoOut | None = None
    manageable: bool = False  # the caller may change this person's access here
    managed_reason: str | None = None  # why not, when not


class AppUsersOut(BaseModel):
    users: list[AppUserOut]
    default_access_note: str | None = None


class PersonOut(BaseModel):
    user_id: int | None = None
    entra_object_id: str | None = None  # set for a directory employee not yet in DijiOne
    full_name: str
    email: str
    job_title: str | None = None
    department: str | None = None
    source: str  # DIJIONE / DIRECTORY
    has_access: bool = False
    role_name: str | None = None
    can_grant: bool = False
    reason: str | None = None


class PeopleOut(BaseModel):
    people: list[PersonOut]
    directory_available: bool = True


class GrantIn(BaseModel):
    role: str = Field(min_length=1, max_length=64)
    client_scope: ClientScopeIn | None = None


class OnboardIn(GrantIn):
    entra_object_id: str = Field(min_length=36, max_length=36)


class RevokeIn(BaseModel):
    reason: str = Field(default="", max_length=500)


class RevokePreviewOut(BaseModel):
    allowed: bool
    reason: str | None = None
    removes_direct: AccessSourceOut | None = None
    suspends: list[AccessSourceOut] = []
    keeps: list[AccessSourceOut] = []  # mandatory access that stays


class AppointIn(BaseModel):
    grantable_roles: list[str] = Field(default_factory=list, max_length=20)
    client_authority: ClientScopeIn | None = None  # required for client-scoped applications
    can_appoint_admins: bool = False
    break_glass_reason: str | None = Field(default=None, max_length=500)


class AdministratorOut(BaseModel):
    user_id: int
    full_name: str
    email: str
    can_appoint_admins: bool
    grantable_roles: list[AccessRoleOut]
    client_authority: AccessScopeOut | None = None
    appointed_by_name: str | None = None
    appointed_at: datetime
    eligible_employee: bool = True  # an appointment applies only while the person is eligible


class ModuleEnabledIn(BaseModel):
    enabled: bool
