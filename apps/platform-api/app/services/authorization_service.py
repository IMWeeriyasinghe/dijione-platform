"""Centralized DijiOne authorization engine (Phase 2 CR §32).

Resolves, from database state only, what an authenticated user may do:

    Platform Role       -> platform_permissions()
    Module Assignment    -> module_role_permissions() / client_scope_for()

Never trusts client-supplied role, permission, or client_id values — every
method here takes a already-authenticated ``User`` or ``UserModuleRole`` row
loaded by the caller from the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.access_group import (
    AccessGroup,
    AccessGroupStatus,
    GroupModuleClientScope,
    GroupModuleRole,
    UserGroupMembership,
)
from app.models.role import Permission, Role, RolePermission
from app.models.user import User, UserModuleRole
from app.models.user_module_client_scope import UserModuleClientScope


@dataclass(frozen=True)
class ResolvedGrant:
    """One contributing role grant for a user+module, either their own
    direct assignment or one inherited from an active access group."""

    role: str
    source_type: Literal["DIRECT", "GROUP"]
    source_name: str | None = None


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

    # --- Access Groups (Phase 2.6, additive) --------------------------------

    def groups_for_user(self, user_id: int) -> list[AccessGroup]:
        """Active groups the user is a member of. Inactive groups and
        memberships in them contribute nothing to effective access."""
        stmt = (
            select(AccessGroup)
            .join(UserGroupMembership, UserGroupMembership.access_group_id == AccessGroup.id)
            .where(
                UserGroupMembership.user_id == user_id,
                AccessGroup.status == AccessGroupStatus.ACTIVE,
            )
        )
        return list(self.db.execute(stmt).scalars().all())

    def effective_module_roles(self, user: User) -> dict[str, list[ResolvedGrant]]:
        """Combine direct ``UserModuleRole`` grants with ``GroupModuleRole``
        grants from every active group the user belongs to (additive ALLOW,
        no DENY semantics — see docs/platform/access-groups.md)."""
        grants: dict[str, list[ResolvedGrant]] = {}

        direct_stmt = select(UserModuleRole).where(
            UserModuleRole.user_id == user.id, UserModuleRole.enabled.is_(True)
        )
        for mr in self.db.execute(direct_stmt).scalars().all():
            grants.setdefault(mr.module_key, []).append(
                ResolvedGrant(role=mr.role, source_type="DIRECT", source_name=None)
            )

        groups = self.groups_for_user(user.id)
        if groups:
            group_ids = [g.id for g in groups]
            group_names = {g.id: g.display_name for g in groups}
            group_stmt = select(GroupModuleRole).where(
                GroupModuleRole.access_group_id.in_(group_ids), GroupModuleRole.enabled.is_(True)
            )
            for gr in self.db.execute(group_stmt).scalars().all():
                grants.setdefault(gr.module_key, []).append(
                    ResolvedGrant(
                        role=gr.role, source_type="GROUP", source_name=group_names.get(gr.access_group_id)
                    )
                )

        return grants

    def effective_client_scope(
        self, user: User, module_key: str
    ) -> tuple[list[int] | None, list[ResolvedGrant]]:
        """Union client scope across every contributing assignment (direct
        or group) for ``module_key``. If any contributing assignment is
        unrestricted (``all_clients=True`` or has no scope rows at all —
        the same pre-Phase-2 back-compat default as ``client_scope_for``),
        the effective scope is ALL_CLIENTS (``None``). Otherwise the union
        of every contributing assignment's concrete client ids."""
        sources: list[ResolvedGrant] = []
        client_ids: set[int] = set()
        unrestricted = False

        direct_stmt = select(UserModuleRole).where(
            UserModuleRole.user_id == user.id,
            UserModuleRole.module_key == module_key,
            UserModuleRole.enabled.is_(True),
        )
        for mr in self.db.execute(direct_stmt).scalars().all():
            sources.append(ResolvedGrant(role=mr.role, source_type="DIRECT", source_name=None))
            scope = self.client_scope_for(mr)
            if scope is None:
                unrestricted = True
            else:
                client_ids.update(scope)

        for group in self.groups_for_user(user.id):
            group_stmt = select(GroupModuleRole).where(
                GroupModuleRole.access_group_id == group.id,
                GroupModuleRole.module_key == module_key,
                GroupModuleRole.enabled.is_(True),
            )
            for gr in self.db.execute(group_stmt).scalars().all():
                sources.append(ResolvedGrant(role=gr.role, source_type="GROUP", source_name=group.display_name))
                scope_stmt = select(GroupModuleClientScope).where(
                    GroupModuleClientScope.group_module_role_id == gr.id
                )
                scope_rows = list(self.db.execute(scope_stmt).scalars().all())
                if not scope_rows or any(s.all_clients for s in scope_rows):
                    unrestricted = True
                else:
                    client_ids.update(s.client_id for s in scope_rows if s.client_id is not None)

        if not sources:
            return None, sources
        if unrestricted:
            return None, sources
        return sorted(client_ids), sources

    def effective_permissions(self, user: User, module_key: str) -> frozenset[str]:
        """Union of permissions across every distinct role contributing to
        ``module_key`` for this user (direct + group)."""
        grants = self.effective_module_roles(user).get(module_key, [])
        roles = {g.role for g in grants}
        permissions: set[str] = set()
        for role in roles:
            permissions |= self._permissions_for(module_key, role)
        return frozenset(permissions)
