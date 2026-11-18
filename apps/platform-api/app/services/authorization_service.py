"""Centralized DijiOne authorization engine (Phase 2 CR §32).

Resolves, from database state only, what an authenticated user may do:

    Platform Role       -> platform_permissions()
    Module Assignment    -> module_role_permissions() / client_scope_for()

Never trusts client-supplied role, permission, or client_id values — every
method here takes a already-authenticated ``User`` or ``UserModuleRole`` row
loaded by the caller from the database.

Effective-access precedence for one person and one application (every caller —
session claims, ``/me``, Home, effective access, diagnostics, live permissions,
role holders — goes through ``_contributions``, so they can never disagree):

1. The application is disabled in the registry: nothing applies.
2. Mandatory grants always apply while their own conditions hold: default employee
   access (``BASELINE``, eligible employees) and grants from ``SYSTEM`` groups.
3. An application suspension removes every other grant for that application:
   direct assignments, ordinary group grants and the administrator appointment.
4. Otherwise every grant applies (additive ALLOW, no DENY other than 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DELEGATION
from app.models.access_group import (
    AccessGroup,
    AccessGroupStatus,
    GroupModuleClientScope,
    GroupModuleRole,
    UserGroupMembership,
)
from app.models.application_access import ApplicationAccessSuspension, ApplicationAdministrator
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.role import Permission, Role, RolePermission
from app.models.user import User, UserModuleRole
from app.models.user_module_client_scope import UserModuleClientScope

# Employee-record states that qualify for default employee access (see is_eligible_employee).
ELIGIBLE_RECORD_STATUSES = frozenset({"MATCHED", "LEGACY"})
SYSTEM_GROUP_TYPE = "SYSTEM"

SourceType = Literal["DIRECT", "GROUP", "BASELINE", "APPOINTMENT"]


@dataclass(frozen=True)
class ResolvedGrant:
    """One contributing role grant for a user+module: their own direct assignment, one
    inherited from an active access group, default employee access, or an administrator
    appointment. ``mandated`` grants are never removed by an application suspension."""

    role: str
    source_type: SourceType
    source_name: str | None = None
    mandated: bool = False
    group_id: int | None = None


@dataclass
class _Contributions:
    """Everything that applies to one user and one application after precedence."""

    grants: list[ResolvedGrant] = field(default_factory=list)
    direct_rows: list[UserModuleRole] = field(default_factory=list)
    group_rows: list[tuple[GroupModuleRole, AccessGroup]] = field(default_factory=list)


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

    def client_ref_scope_for(self, module_role: UserModuleRole) -> list[str] | None:
        """``client_scope_for`` in terms of the durable ``client_ref``
        (a platform-owned ``Client.public_id``) instead of the legacy
        integer. Same ALL_CLIENTS / no-rows semantics."""
        stmt = select(UserModuleClientScope).where(
            UserModuleClientScope.user_module_role_id == module_role.id
        )
        scopes = list(self.db.execute(stmt).scalars().all())
        if not scopes:
            return None
        if any(s.all_clients for s in scopes):
            return None
        return [s.client_ref for s in scopes if s.client_ref is not None]

    def group_client_ref_scope(self, group_role: GroupModuleRole) -> list[str] | None:
        rows = list(
            self.db.execute(
                select(GroupModuleClientScope).where(GroupModuleClientScope.group_module_role_id == group_role.id)
            ).scalars().all()
        )
        if not rows or any(s.all_clients for s in rows):
            return None
        return [s.client_ref for s in rows if s.client_ref is not None]

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

    # --- Precedence (one implementation for every caller) ---------------------

    def disabled_module_keys(self) -> set[str]:
        """Applications explicitly disabled in the registry. (A key with no registry row keeps the
        historical behaviour: its assignments apply.)"""
        return set(self.db.execute(select(ApplicationModule.key).where(ApplicationModule.enabled.is_(False))).scalars())

    def suspended_modules(self, user: User) -> set[str]:
        return set(
            self.db.execute(
                select(ApplicationAccessSuspension.module_key).where(ApplicationAccessSuspension.user_id == user.id)
            ).scalars()
        )

    def appointments(self, user: User) -> list[ApplicationAdministrator]:
        return list(
            self.db.execute(select(ApplicationAdministrator).where(ApplicationAdministrator.user_id == user.id))
            .scalars()
            .all()
        )

    @staticmethod
    def appointment_role(appointment: ApplicationAdministrator) -> str | None:
        definition = DELEGATION.get(appointment.module_key)
        if definition is None:
            return None
        return definition.owner_role if appointment.can_appoint_admins else definition.admin_role

    def _all_contributions(self, user: User) -> dict[str, _Contributions]:
        disabled = self.disabled_module_keys()
        suspended = self.suspended_modules(user)
        out: dict[str, _Contributions] = {}

        def bucket(module_key: str) -> _Contributions:
            return out.setdefault(module_key, _Contributions())

        direct_stmt = select(UserModuleRole).where(UserModuleRole.user_id == user.id, UserModuleRole.enabled.is_(True))
        for mr in self.db.execute(direct_stmt).scalars().all():
            if mr.module_key in disabled or mr.module_key in suspended:
                continue
            b = bucket(mr.module_key)
            b.grants.append(ResolvedGrant(role=mr.role, source_type="DIRECT"))
            b.direct_rows.append(mr)

        groups = self.groups_for_user(user.id)
        if groups:
            by_id = {g.id: g for g in groups}
            group_stmt = select(GroupModuleRole).where(
                GroupModuleRole.access_group_id.in_(list(by_id)), GroupModuleRole.enabled.is_(True)
            )
            for gr in self.db.execute(group_stmt).scalars().all():
                group = by_id[gr.access_group_id]
                mandated = group.group_type == SYSTEM_GROUP_TYPE
                if gr.module_key in disabled or (gr.module_key in suspended and not mandated):
                    continue
                b = bucket(gr.module_key)
                b.grants.append(
                    ResolvedGrant(
                        role=gr.role, source_type="GROUP", source_name=group.display_name, mandated=mandated,
                        group_id=group.id,
                    )
                )
                b.group_rows.append((gr, group))

        for module_key, role in self.baseline_roles(user).items():
            bucket(module_key).grants.append(ResolvedGrant(role=role, source_type="BASELINE", mandated=True))

        if self.is_eligible_employee(user):
            for appointment in self.appointments(user):
                role = self.appointment_role(appointment)
                if role is None or appointment.module_key in disabled or appointment.module_key in suspended:
                    continue
                bucket(appointment.module_key).grants.append(ResolvedGrant(role=role, source_type="APPOINTMENT"))

        return {k: v for k, v in out.items() if v.grants}

    def _contributions(self, user: User, module_key: str) -> _Contributions:
        return self._all_contributions(user).get(module_key, _Contributions())

    def effective_module_roles(self, user: User) -> dict[str, list[ResolvedGrant]]:
        """Every grant that applies, per application, in the order DIRECT, GROUP, BASELINE,
        APPOINTMENT (the claims builder's single ``role`` prefers DIRECT, else the first)."""
        return {k: v.grants for k, v in self._all_contributions(user).items()}

    @staticmethod
    def identity_verified(user: User) -> bool:
        """The person is a verified internal member of our Entra tenant: proven by a verified
        Microsoft sign-in or by directory verification (Microsoft Graph)."""
        return bool(user.internal_employee and user.identity_provider == "ENTRA" and user.entra_object_id)

    @classmethod
    def is_eligible_employee(cls, user: User) -> bool:
        """Active, identity verified, and matched to an employee record (BambooHR), or LEGACY:
        eligible before employee-record checks existed, kept until reconciled. An Entra member
        account with a company address alone (a service account, a shared mailbox) is not enough.
        Gates default employee access, appointments and View-as; explicit assignments never
        depend on it."""
        return bool(
            user.is_active and cls.identity_verified(user) and user.employee_record_status in ELIGIBLE_RECORD_STATUSES
        )

    def baseline_exclusions(self, user: User) -> list[tuple[str, str]]:
        """Default employee access is always on for an eligible employee: nothing excludes it."""
        return []

    def baseline_roles(self, user: User) -> dict[str, str]:
        """Module roles every eligible employee holds. Always on: no assignment, disabled row,
        group change or application suspension removes them while the person stays eligible.
        Additive with any higher role."""
        if not self.is_eligible_employee(user):
            return {}
        rows = self.db.execute(
            select(ModuleBaselineRole.module_key, ModuleBaselineRole.role)
            .join(ApplicationModule, ApplicationModule.key == ModuleBaselineRole.module_key)
            .where(ModuleBaselineRole.enabled.is_(True), ApplicationModule.enabled.is_(True))
        ).all()
        return {module_key: role for module_key, role in rows}

    def effective_client_scope(
        self, user: User, module_key: str
    ) -> tuple[list[int] | None, list[ResolvedGrant]]:
        """Union client scope across every contributing direct or group assignment for
        ``module_key`` (after precedence). If any is unrestricted (``all_clients=True`` or no
        scope rows — the pre-Phase-2 back-compat default), the scope is ALL_CLIENTS (``None``);
        otherwise the union of their client ids. Default access and appointments carry no client
        scope: an application reached only through them yields ``[]`` (no clients)."""
        c = self._contributions(user, module_key)
        sources: list[ResolvedGrant] = [g for g in c.grants if g.source_type in ("DIRECT", "GROUP")]
        client_ids: set[int] = set()
        unrestricted = False
        for mr in c.direct_rows:
            scope = self.client_scope_for(mr)
            if scope is None:
                unrestricted = True
            else:
                client_ids.update(scope)
        for gr, _group in c.group_rows:
            scope_rows = list(
                self.db.execute(
                    select(GroupModuleClientScope).where(GroupModuleClientScope.group_module_role_id == gr.id)
                ).scalars().all()
            )
            if not scope_rows or any(s.all_clients for s in scope_rows):
                unrestricted = True
            else:
                client_ids.update(s.client_id for s in scope_rows if s.client_id is not None)

        if not sources:
            return ([] if c.grants and self._only_unscoped_sources(c) else None), sources
        if unrestricted:
            return None, sources
        return sorted(client_ids), sources

    @staticmethod
    def _only_unscoped_sources(c: _Contributions) -> bool:
        """True when the only grants are appointments (administrator-only roles carry no client
        scope). Default access keeps its historical "no restriction recorded" (``None``)."""
        return all(g.source_type == "APPOINTMENT" for g in c.grants)

    def effective_client_ref_scope(self, user: User, module_key: str) -> list[str] | None:
        """``effective_client_scope`` expressed as durable ``client_ref``
        (platform ``Client.public_id``) values — the union across every
        contributing direct/group assignment, or ``None`` for unrestricted.
        This is what ``claims_service`` embeds as ``client_public_ids``."""
        c = self._contributions(user, module_key)
        if not c.direct_rows and not c.group_rows:
            return [] if c.grants and self._only_unscoped_sources(c) else None
        client_refs: set[str] = set()
        for mr in c.direct_rows:
            scope = self.client_ref_scope_for(mr)
            if scope is None:
                return None
            client_refs.update(scope)
        for gr, _group in c.group_rows:
            scope = self.group_client_ref_scope(gr)
            if scope is None:
                return None
            client_refs.update(scope)
        return sorted(client_refs)

    def effective_permissions(self, user: User, module_key: str) -> frozenset[str]:
        """Union of permissions across every distinct role contributing to
        ``module_key`` for this user, after precedence."""
        grants = self.effective_module_roles(user).get(module_key, [])
        roles = {g.role for g in grants}
        permissions: set[str] = set()
        for role in roles:
            permissions |= self._permissions_for(module_key, role)
        return frozenset(permissions)

    def holds_role(self, user: User, module_key: str, role: str) -> bool:
        """Whether the role applies to the user in that application, from any source."""
        return user.is_active and any(g.role == role for g in self.effective_module_roles(user).get(module_key, []))
