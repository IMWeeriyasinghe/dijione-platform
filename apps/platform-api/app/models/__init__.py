from app.db.base import Base
from app.models.access_group import (
    AccessGroup,
    GroupModuleClientScope,
    GroupModuleRole,
    UserGroupMembership,
)
from app.models.audit_log import AuditLog
from app.models.client import Client, ClientExternalId, ClientStatus
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.notification import Notification
from app.models.protected_admin import ProtectedAdmin
from app.models.role import Permission, Role, RolePermission
from app.models.user import User, UserModuleRole
from app.models.user_module_client_scope import UserModuleClientScope
from app.models.view_as_session import ViewAsSession

__all__ = [
    "ModuleBaselineRole",
    "Base",
    "AuditLog",
    "Client",
    "ClientExternalId",
    "ClientStatus",
    "ApplicationModule",
    "Notification",
    "Permission",
    "Role",
    "RolePermission",
    "User",
    "UserModuleRole",
    "ViewAsSession",
    "ProtectedAdmin",
    "UserModuleClientScope",
    "AccessGroup",
    "UserGroupMembership",
    "GroupModuleRole",
    "GroupModuleClientScope",
]

# Registers the listener that keeps ``users.access_version`` in step with every
# access change. Imported last: it depends on the models above.
from app.services import access_version as _access_version  # noqa: E402,F401
from app.services import protected_admin as _protected_admin  # noqa: E402,F401
