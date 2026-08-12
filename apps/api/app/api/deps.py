from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.constants import MODULE_TALENT_FLOW
from app.core.security import InvalidTokenError, get_auth_provider
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.services.authorization_service import AuthorizationService

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = get_auth_provider().decode_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc

    user_id = int(payload["sub"])
    user = UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_platform_admin(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    """Any DijiOne Admin Center access (SUPER_ADMIN or PLATFORM_ADMIN)."""
    permissions = AuthorizationService(db).platform_permissions(user)
    if "platform.admin.access" not in permissions:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform admin access required")
    return user


def require_platform_permission(permission_key: str):
    """Reusable factory for platform-level (Admin Center) permission gates
    (CLAUDE.md-extension §32). Example: ``Depends(require_platform_permission(
    "platform.admin.manage_admins"))`` for SUPER_ADMIN-only actions."""

    def _dependency(
        user: User = Depends(get_current_user), db: Session = Depends(get_db)
    ) -> User:
        permissions = AuthorizationService(db).platform_permissions(user)
        if permission_key not in permissions:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Missing required permission: {permission_key}"
            )
        return user

    return _dependency


@dataclass
class TalentScope:
    """Resolved DijiTalentFlow authorization scope for the current user.

    ``client_id`` is not-None for TALENT_CLIENT personas — every
    tenant-scoped repository call must pass it through. It is None for
    staff roles.

    ``client_ids`` is the staff *portfolio* restriction (CLAUDE.md-extension
    §22): ``None`` means unrestricted (ALL_CLIENTS) cross-client access; a
    list means the staff member may only see those specific clients. It is
    only meaningful when ``client_id`` is None.

    ``permissions`` is the resolved, module-scoped permission set backing
    every authorization decision in this scope — role-name checks
    (``is_staff`` etc.) are thin convenience wrappers over it, not a
    separate source of truth.
    """

    user: User
    role: str
    client_id: int | None
    client_ids: list[int] | None = field(default=None)
    permissions: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_staff(self) -> bool:
        return "talent.workspace.staff" in self.permissions

    def has(self, permission_key: str) -> bool:
        return permission_key in self.permissions


def get_talent_scope(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> TalentScope:
    module_role = UserRepository(db).module_role_for(user.id, MODULE_TALENT_FLOW)
    if module_role is None or not module_role.enabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "User has no active DijiTalentFlow module access"
        )
    authz = AuthorizationService(db)
    return TalentScope(
        user=user,
        role=module_role.role,
        client_id=module_role.client_id,
        client_ids=authz.client_scope_for(module_role),
        permissions=authz.module_role_permissions(module_role),
    )


def require_staff_scope(scope: TalentScope = Depends(get_talent_scope)) -> TalentScope:
    if not scope.is_staff:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This action requires a Talent Acquisition or Customer Success role"
        )
    return scope


def require_customer_success_scope(scope: TalentScope = Depends(get_talent_scope)) -> TalentScope:
    if not scope.has("talent.requests.review"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This action requires the talent.requests.review permission"
        )
    return scope


def require_talent_permission(permission_key: str):
    """Reusable factory for DijiTalentFlow route-level permission gates."""

    def _dependency(scope: TalentScope = Depends(get_talent_scope)) -> TalentScope:
        if not scope.has(permission_key):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Missing required permission: {permission_key}"
            )
        return scope

    return _dependency
