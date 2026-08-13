"""Centralized DijiOne authorization engine (Phase 2 CR §32).

Resolves, from database state only, what an authenticated user may do:

    Platform Role       -> platform_permissions()
    Module Assignment    -> module_role_permissions() / client_scope_for()

Never trusts client-supplied role, permission, or client_id values — every
method here takes a already-authenticated ``User`` or ``UserModuleRole`` row
loaded by the caller from the database.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.role import Permission, Role, RolePermission
from app.models.user import User, UserModuleRole
from app.models.user_module_client_scope import UserModuleClientScope


class AuthorizationService:
    def __init__(self, db: Session):
        self.db = db

    def _permissions_for(self, module_key: str | None, role_key: str) -> frozenset[str]:
        stmt = (
            select(Permission.key)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .where(Role.key == role_key)
        )
        stmt = stmt.where(Role.module_key.is_(None)) if module_key is None else stmt.where(
            Role.module_key == module_key
        )
        return frozenset(self.db.execute(stmt).scalars().all())

    def platform_permissions(self, user: User) -> frozenset[str]:
        """Permissions granted by the user's platform role (SUPER_ADMIN /
        PLATFORM_ADMIN / PLATFORM_USER). Inactive users should never reach
        here — callers must check ``User.is_active`` first."""
        return self._permissions_for(None, user.platform_role)

    def module_role_permissions(self, module_role: UserModuleRole) -> frozenset[str]:
        """Permissions granted by a module assignment's role."""
        return self._permissions_for(module_role.module_key, module_role.role)

    def client_scope_for(self, module_role: UserModuleRole) -> list[int] | None:
        """Resolve the client/portfolio scope for a module assignment.

        Returns ``None`` for unrestricted (ALL_CLIENTS) access, or the list
        of authorized client ids otherwise. A module assignment with no
        recorded scope rows at all is treated as unrestricted — this is the
        pre-Phase-2 default for staff roles and keeps old data working
        without a mandatory backfill for every row.
        """
        stmt = select(UserModuleClientScope).where(
            UserModuleClientScope.user_module_role_id == module_role.id
        )
        scopes = list(self.db.execute(stmt).scalars().all())
        if not scopes:
            return None
        if any(s.all_clients for s in scopes):
            return None
        return [s.client_id for s in scopes if s.client_id is not None]

    def role_display(self, module_key: str | None, role_key: str) -> Role | None:
        stmt = select(Role).where(Role.key == role_key)
        stmt = stmt.where(Role.module_key.is_(None)) if module_key is None else stmt.where(
            Role.module_key == module_key
        )
        return self.db.execute(stmt).scalars().first()
