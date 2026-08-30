"""Platform Core's raw administration primitives (Phase 2 CR §11-31, adapted
for Phase 2.5 service separation).

This is the *only* code path that mutates platform-owned tables (users,
module role assignments, client-scope rows, the module registry, the audit
log) on behalf of an administrator. admin-api has no database of its own —
every `/api/admin/*` request it receives is forwarded here as
`/api/platform/admin/*`, authorized with the *original caller's* bearer
token (never a service-to-service secret), so the exact same
``require_platform_admin``/``require_platform_permission`` dependencies this
module always used still gate every mutation (CR §48: never trust a role/
user id supplied by another service).

What changed from the pre-split ``AdminService``: this service can no
longer resolve DijiTalentFlow client *names* (``Client`` lives in
talent-api's own database now) or the live pending-talent-request count —
those fields are always returned empty/zero here. admin-api enriches both
by separately calling talent-api's summary/clients-lite endpoints and
merging before responding to the browser, so the public `/api/admin/*`
contract app-web/admin-web sees is unchanged. See
``docs/platform/service-contracts.md``.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import MODULE_BIRTHDAY, MODULE_SPARK, MODULE_TALENT_FLOW, PlatformRole
from app.models.access_group import (
    AccessGroup,
    AccessGroupStatus,
    GroupModuleClientScope,
    GroupModuleRole,
    UserGroupMembership,
)
from app.models.module import ApplicationModule
from app.models.role import Permission, Role, RolePermission
from app.models.user import User, UserModuleRole
from app.models.user_module_client_scope import UserModuleClientScope
from app.schemas.admin import (
    AccessGroupDetailOut,
    AccessGroupOut,
    AccessSourceOut,
    AdminDashboardOut,
    AdminModuleOut,
    AdminPermissionOut,
    AdminRoleOut,
    AdminUserOut,
    ApplicationAssignedGroupOut,
    ApplicationAssignedUserOut,
    ApplicationDetailOut,
    AuditLogOut,
    ClientScopeIn,
    ClientScopeOut,
    EffectiveAccessOut,
    EffectiveModuleAccessOut,
    GroupMemberOut,
    GroupModuleAssignmentOut,
    ModuleAssignmentOut,
)
from app.services import client_directory
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthorizationService

ADMIN_PLATFORM_ROLES = {PlatformRole.SUPER_ADMIN.value, PlatformRole.PLATFORM_ADMIN.value}

_MODULE_DISPLAY_ORDER = [MODULE_TALENT_FLOW, MODULE_BIRTHDAY, MODULE_SPARK]

# Audit entity_type convention for group mutations (Phase 2.6): group
# lifecycle/module-assignment changes use entity_type="AccessGroup" with the
# group's id as entity_id; membership changes use entity_type=
# "UserGroupMembership" with the membership row's id as entity_id, since
# they concern a (user, group) pair rather than the group alone.


class AdminError(Exception):
    pass


class NotFoundError(AdminError):
    pass


class ForbiddenError(AdminError):
    """Raised for authorization decisions the route layer should map to 403,
    distinct from FastAPI dependency-level permission gates — used for
    business-rule checks that need the *target* record loaded first (e.g.
    SUPER_ADMIN lockout), which a plain Depends() can't express."""


class LastSuperAdminError(ForbiddenError):
    pass


class SystemGroupProtectedError(ForbiddenError):
    """SYSTEM access groups cannot be deleted or deactivated (mirrors the
    LastSuperAdminError guard-rail pattern above)."""


class AdminService:
    def __init__(self, db: Session):
        self.db = db
        self.authz = AuthorizationService(db)
        self.audit = AuditService(db)

    @staticmethod
    def _validate_client_scope(client_scope: ClientScopeIn | None) -> None:
        """Temporary guard (Architecture v2 §9): a concrete client_id in a
        module/group scope must actually exist in talent-api. Fail-safe —
        ``ClientDirectoryUnavailableError`` (talent-api unreachable) propagates
        to the route as a 503; an unknown id becomes an ``AdminError`` (400)."""
        if client_scope is None or client_scope.all_clients or not client_scope.client_ids:
            return
        try:
            client_directory.validate_client_ids(client_scope.client_ids)
        except client_directory.UnknownClientIdError as exc:
            raise AdminError(str(exc)) from exc

    # --- Users -----------------------------------------------------------

    def _module_names(self) -> dict[str, str]:
        rows = self.db.execute(select(ApplicationModule.key, ApplicationModule.name)).all()
        return dict(rows)

    def _to_module_assignment_out(
        self, module_role: UserModuleRole, module_names: dict[str, str]
    ) -> ModuleAssignmentOut:
        role_row = self.authz.role_display(module_role.module_key, module_role.role)
        client_ids = self.authz.client_scope_for(module_role)
        all_clients = client_ids is None
        return ModuleAssignmentOut(
            module_key=module_role.module_key,
            module_name=module_names.get(module_role.module_key, module_role.module_key),
            role=module_role.role,
            role_name=role_row.name if role_row else module_role.role,
            enabled=module_role.enabled,
            client_scope=ClientScopeOut(
                all_clients=all_clients,
                client_ids=client_ids or [],
                # Client *names* are resolved by admin-api from talent-api,
                # not here — Platform Core doesn't own the Client table.
                client_names=[],
            ),
        )

    def to_user_out(self, user: User) -> AdminUserOut:
        module_names = self._module_names()
        stmt = select(UserModuleRole).where(UserModuleRole.user_id == user.id)
        module_roles = list(self.db.execute(stmt).scalars().all())
        return AdminUserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            title=user.title,
            platform_role=user.platform_role,
            is_active=user.is_active,
            identity_provider=user.identity_provider,
            entra_object_id=user.entra_object_id,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            module_assignments=[self._to_module_assignment_out(mr, module_names) for mr in module_roles],
        )

    def list_users(self) -> list[AdminUserOut]:
        users = list(self.db.execute(select(User).order_by(User.full_name)).scalars().all())
        return [self.to_user_out(u) for u in users]

    def get_user(self, user_id: int) -> AdminUserOut:
        user = self.db.get(User, user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return self.to_user_out(user)

    def _active_super_admin_count(self, *, excluding_user_id: int | None = None) -> int:
        stmt = select(func.count(User.id)).where(
            User.platform_role == PlatformRole.SUPER_ADMIN.value, User.is_active.is_(True)
        )
        if excluding_user_id is not None:
            stmt = stmt.where(User.id != excluding_user_id)
        return self.db.execute(stmt).scalar_one()

    def set_user_active(self, *, actor: User, target_user_id: int, is_active: bool) -> AdminUserOut:
        target = self.db.get(User, target_user_id)
        if target is None:
            raise NotFoundError(f"User {target_user_id} not found")

        if (
            not is_active
            and target.platform_role == PlatformRole.SUPER_ADMIN.value
            and self._active_super_admin_count(excluding_user_id=target.id) == 0
        ):
            raise LastSuperAdminError("Cannot deactivate the last active SUPER_ADMIN")

        previous = target.is_active
        target.is_active = is_active
        self.db.flush()
        self.audit.log(
            actor_id=actor.id,
            action="user.activated" if is_active else "user.deactivated",
            entity_type="User",
            entity_id=target.id,
            previous_state={"is_active": previous},
            new_state={"is_active": is_active},
        )
        self.db.commit()
        return self.to_user_out(target)

    def set_platform_role(self, *, actor: User, target_user_id: int, new_role: str) -> AdminUserOut:
        target = self.db.get(User, target_user_id)
        if target is None:
            raise NotFoundError(f"User {target_user_id} not found")
        if new_role not in {r.value for r in PlatformRole}:
            raise AdminError(f"Unknown platform role: {new_role}")

        touches_admin_roles = (
            target.platform_role in ADMIN_PLATFORM_ROLES or new_role in ADMIN_PLATFORM_ROLES
        )
        if touches_admin_roles:
            actor_permissions = self.authz.platform_permissions(actor)
            if "platform.admin.manage_admins" not in actor_permissions:
                raise ForbiddenError(
                    "Only a SUPER_ADMIN may grant, change, or revoke administrator privileges"
                )

        if (
            target.platform_role == PlatformRole.SUPER_ADMIN.value
            and new_role != PlatformRole.SUPER_ADMIN.value
            and self._active_super_admin_count(excluding_user_id=target.id) == 0
        ):
            raise LastSuperAdminError("Cannot demote the last active SUPER_ADMIN")

        previous = target.platform_role
        target.platform_role = new_role
        self.db.flush()
        self.audit.log(
            actor_id=actor.id,
            action="user.platform_role_changed",
            entity_type="User",
            entity_id=target.id,
            previous_state={"platform_role": previous},
            new_state={"platform_role": new_role},
        )
        self.db.commit()
        return self.to_user_out(target)

    # --- Module assignments ------------------------------------------------

    def upsert_module_assignment(
        self,
        *,
        actor: User,
        target_user_id: int,
        module_key: str,
        role: str,
        enabled: bool,
        client_scope: ClientScopeIn | None,
    ) -> AdminUserOut:
        target = self.db.get(User, target_user_id)
        if target is None:
            raise NotFoundError(f"User {target_user_id} not found")

        role_row = self.authz.role_display(module_key, role)
        if role_row is None:
            raise AdminError(f"Unknown role '{role}' for module '{module_key}'")
        self._validate_client_scope(client_scope)

        stmt = select(UserModuleRole).where(
            UserModuleRole.user_id == target_user_id, UserModuleRole.module_key == module_key
        )
        module_role = self.db.execute(stmt).scalars().first()
        previous_state = None
        if module_role is None:
            module_role = UserModuleRole(user_id=target_user_id, module_key=module_key, role=role, enabled=enabled)
            self.db.add(module_role)
            self.db.flush()
            action = "module_assignment.created"
        else:
            previous_state = {"role": module_role.role, "enabled": module_role.enabled}
            module_role.role = role
            module_role.enabled = enabled
            # TALENT_CLIENT keeps its legacy single-tenant client_id in sync
            # for backward compatibility with code paths that still read it.
            if client_scope is not None and not client_scope.all_clients and len(client_scope.client_ids) == 1:
                module_role.client_id = client_scope.client_ids[0]
            elif client_scope is not None:
                module_role.client_id = None
            action = "module_assignment.updated"

        if client_scope is not None:
            self.db.execute(
                UserModuleClientScope.__table__.delete().where(
                    UserModuleClientScope.user_module_role_id == module_role.id
                )
            )
            if client_scope.all_clients:
                self.db.add(UserModuleClientScope(user_module_role_id=module_role.id, all_clients=True))
            else:
                for client_id in client_scope.client_ids:
                    self.db.add(
                        UserModuleClientScope(
                            user_module_role_id=module_role.id, client_id=client_id, all_clients=False
                        )
                    )

        self.db.flush()
        self.audit.log(
            actor_id=actor.id,
            action=action,
            entity_type="UserModuleRole",
            entity_id=module_role.id,
            previous_state=previous_state,
            new_state={
                "user_id": target_user_id, "module_key": module_key, "role": role, "enabled": enabled,
                "client_scope": (
                    "ALL_CLIENTS" if client_scope and client_scope.all_clients
                    else (client_scope.client_ids if client_scope else None)
                ),
            },
        )
        self.db.commit()
        return self.to_user_out(target)

    def remove_module_assignment(self, *, actor: User, target_user_id: int, module_key: str) -> AdminUserOut:
        target = self.db.get(User, target_user_id)
        if target is None:
            raise NotFoundError(f"User {target_user_id} not found")
        stmt = select(UserModuleRole).where(
            UserModuleRole.user_id == target_user_id, UserModuleRole.module_key == module_key
        )
        module_role = self.db.execute(stmt).scalars().first()
        if module_role is None:
            raise NotFoundError(f"User {target_user_id} has no assignment for module '{module_key}'")

        self.audit.log(
            actor_id=actor.id,
            action="module_assignment.removed",
            entity_type="UserModuleRole",
            entity_id=module_role.id,
            previous_state={"module_key": module_key, "role": module_role.role},
        )
        self.db.delete(module_role)
        self.db.commit()
        return self.to_user_out(target)

    # --- Modules / Roles / Permissions catalog ------------------------------

    def list_modules(self) -> list[AdminModuleOut]:
        modules = list(
            self.db.execute(select(ApplicationModule).order_by(ApplicationModule.display_order)).scalars().all()
        )
        counts = dict(
            self.db.execute(
                select(UserModuleRole.module_key, func.count(UserModuleRole.id)).group_by(
                    UserModuleRole.module_key
                )
            ).all()
        )
        return [
            AdminModuleOut(
                id=m.id, key=m.key, name=m.name, description=m.description, icon=m.icon, route=m.route,
                status=m.status, enabled=m.enabled, display_order=m.display_order,
                user_count=counts.get(m.key, 0),
            )
            for m in modules
        ]

    def list_roles(self) -> list[AdminRoleOut]:
        roles = list(self.db.execute(select(Role).order_by(Role.module_key.nulls_first(), Role.name)).scalars().all())
        permission_counts = dict(
            self.db.execute(
                select(RolePermission.role_id, func.count(RolePermission.permission_id)).group_by(
                    RolePermission.role_id
                )
            ).all()
        )
        platform_user_counts = dict(
            self.db.execute(select(User.platform_role, func.count(User.id)).group_by(User.platform_role)).all()
        )
        module_user_counts = dict(
            self.db.execute(
                select(UserModuleRole.role, func.count(UserModuleRole.id)).group_by(UserModuleRole.role)
            ).all()
        )
        out = []
        for r in roles:
            user_count = platform_user_counts.get(r.key, 0) if r.module_key is None else module_user_counts.get(r.key, 0)
            out.append(
                AdminRoleOut(
                    id=r.id, module_key=r.module_key, key=r.key, name=r.name, description=r.description,
                    is_system=r.is_system, permission_count=permission_counts.get(r.id, 0), user_count=user_count,
                )
            )
        return out

    def list_permissions(self) -> list[AdminPermissionOut]:
        permissions = list(
            self.db.execute(select(Permission).order_by(Permission.category, Permission.name)).scalars().all()
        )
        return [
            AdminPermissionOut(
                id=p.id, key=p.key, name=p.name, description=p.description, module_key=p.module_key,
                category=p.category,
            )
            for p in permissions
        ]

    # --- Audit ------------------------------------------------------------

    def list_audit(self, *, limit: int = 200, entity_type: str | None = None) -> list[AuditLogOut]:
        from app.models.audit_log import AuditLog

        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        entries = list(self.db.execute(stmt).scalars().all())
        actor_ids = {e.actor_id for e in entries if e.actor_id is not None}
        actor_names = dict(
            self.db.execute(select(User.id, User.full_name).where(User.id.in_(actor_ids))).all()
        ) if actor_ids else {}
        return [
            AuditLogOut(
                id=e.id, actor_id=e.actor_id, actor_name=actor_names.get(e.actor_id),
                action=e.action, entity_type=e.entity_type, entity_id=e.entity_id,
                previous_state=e.previous_state, new_state=e.new_state, metadata=e.event_metadata,
                created_at=e.created_at,
            )
            for e in entries
        ]

    # --- Effective access ---------------------------------------------------

    def effective_access(self, user_id: int) -> EffectiveAccessOut:
        user = self.db.get(User, user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")

        module_names = self._module_names()
        grants_by_module = self.authz.effective_module_roles(user)

        modules_out = []
        for module_key, grants in grants_by_module.items():
            # Back-compat single role/name: prefer a DIRECT grant when one
            # exists (matches pre-group behavior exactly), else the first
            # GROUP grant. See claims_service.build_claims for the same
            # documented precedence choice.
            primary = next((g for g in grants if g.source_type == "DIRECT"), grants[0])
            role_row = self.authz.role_display(module_key, primary.role)
            permissions = sorted(self.authz.effective_permissions(user, module_key))
            client_ids, scope_sources = self.authz.effective_client_scope(user, module_key)
            enabled = True  # only enabled grants are ever collected by effective_module_roles
            sources = [
                AccessSourceOut(type=g.source_type, role=g.role, group_name=g.source_name)
                for g in grants
            ]
            modules_out.append(
                EffectiveModuleAccessOut(
                    module_key=module_key,
                    module_name=module_names.get(module_key, module_key),
                    enabled=enabled,
                    role=primary.role,
                    role_name=role_row.name if role_row else primary.role,
                    client_scope=ClientScopeOut(
                        all_clients=client_ids is None,
                        client_ids=client_ids or [],
                        client_names=[],
                    ),
                    permissions=permissions,
                    sources=sources,
                )
            )

        return EffectiveAccessOut(
            user_id=user.id,
            full_name=user.full_name,
            platform_role=user.platform_role,
            is_active=user.is_active,
            platform_permissions=sorted(self.authz.platform_permissions(user)),
            modules=modules_out,
        )

    # --- Access Groups (Phase 2.6, additive) --------------------------------

    def _group_counts(self) -> tuple[dict[int, int], dict[int, int]]:
        member_counts = dict(
            self.db.execute(
                select(UserGroupMembership.access_group_id, func.count(UserGroupMembership.id)).group_by(
                    UserGroupMembership.access_group_id
                )
            ).all()
        )
        module_counts = dict(
            self.db.execute(
                select(GroupModuleRole.access_group_id, func.count(GroupModuleRole.id)).group_by(
                    GroupModuleRole.access_group_id
                )
            ).all()
        )
        return member_counts, module_counts

    def _to_group_out(self, group: AccessGroup, member_counts: dict, module_counts: dict) -> AccessGroupOut:
        return AccessGroupOut(
            id=group.id, key=group.key, display_name=group.display_name, description=group.description,
            status=group.status, group_type=group.group_type,
            member_count=member_counts.get(group.id, 0), module_count=module_counts.get(group.id, 0),
            created_at=group.created_at, updated_at=group.updated_at,
        )

    def list_groups(self) -> list[AccessGroupOut]:
        groups = list(self.db.execute(select(AccessGroup).order_by(AccessGroup.display_name)).scalars().all())
        member_counts, module_counts = self._group_counts()
        return [self._to_group_out(g, member_counts, module_counts) for g in groups]

    def _get_group_or_404(self, group_id: int) -> AccessGroup:
        group = self.db.get(AccessGroup, group_id)
        if group is None:
            raise NotFoundError(f"Access group {group_id} not found")
        return group

    def get_group(self, group_id: int) -> AccessGroupDetailOut:
        group = self._get_group_or_404(group_id)
        return self._to_group_detail_out(group)

    def _to_group_detail_out(self, group: AccessGroup) -> AccessGroupDetailOut:
        module_names = self._module_names()
        member_stmt = (
            select(User)
            .join(UserGroupMembership, UserGroupMembership.user_id == User.id)
            .where(UserGroupMembership.access_group_id == group.id)
            .order_by(User.full_name)
        )
        members = [
            GroupMemberOut(user_id=u.id, email=u.email, full_name=u.full_name)
            for u in self.db.execute(member_stmt).scalars().all()
        ]
        role_stmt = select(GroupModuleRole).where(GroupModuleRole.access_group_id == group.id)
        module_assignments = []
        for gr in self.db.execute(role_stmt).scalars().all():
            role_row = self.authz.role_display(gr.module_key, gr.role)
            client_ids = self._group_client_scope(gr)
            module_assignments.append(
                GroupModuleAssignmentOut(
                    module_key=gr.module_key,
                    module_name=module_names.get(gr.module_key, gr.module_key),
                    role=gr.role,
                    role_name=role_row.name if role_row else gr.role,
                    enabled=gr.enabled,
                    client_scope=ClientScopeOut(
                        all_clients=client_ids is None, client_ids=client_ids or [], client_names=[]
                    ),
                )
            )
        return AccessGroupDetailOut(
            id=group.id, key=group.key, display_name=group.display_name, description=group.description,
            status=group.status, group_type=group.group_type,
            created_at=group.created_at, updated_at=group.updated_at,
            members=members, module_assignments=module_assignments,
        )

    def _group_client_scope(self, group_module_role: GroupModuleRole) -> list[int] | None:
        stmt = select(GroupModuleClientScope).where(
            GroupModuleClientScope.group_module_role_id == group_module_role.id
        )
        scopes = list(self.db.execute(stmt).scalars().all())
        if not scopes:
            return None
        if any(s.all_clients for s in scopes):
            return None
        return [s.client_id for s in scopes if s.client_id is not None]

    def create_group(
        self, *, actor: User, key: str, display_name: str, description: str = "", group_type: str = "TEAM"
    ) -> AccessGroupDetailOut:
        existing = self.db.execute(select(AccessGroup).where(AccessGroup.key == key)).scalars().first()
        if existing is not None:
            raise AdminError(f"Access group key '{key}' already exists")
        group = AccessGroup(
            key=key, display_name=display_name, description=description, group_type=group_type,
            status=AccessGroupStatus.ACTIVE,
        )
        self.db.add(group)
        self.db.flush()
        self.audit.log(
            actor_id=actor.id, action="access_group.created", entity_type="AccessGroup", entity_id=group.id,
            new_state={"key": key, "display_name": display_name, "group_type": group_type},
        )
        self.db.commit()
        return self._to_group_detail_out(group)

    def update_group(
        self, *, actor: User, group_id: int, display_name: str | None, description: str | None,
        group_type: str | None,
    ) -> AccessGroupDetailOut:
        group = self._get_group_or_404(group_id)
        previous = {
            "display_name": group.display_name, "description": group.description, "group_type": group.group_type,
        }
        if display_name is not None:
            group.display_name = display_name
        if description is not None:
            group.description = description
        if group_type is not None:
            group.group_type = group_type
        self.db.flush()
        self.audit.log(
            actor_id=actor.id, action="access_group.updated", entity_type="AccessGroup", entity_id=group.id,
            previous_state=previous,
            new_state={
                "display_name": group.display_name, "description": group.description,
                "group_type": group.group_type,
            },
        )
        self.db.commit()
        return self._to_group_detail_out(group)

    def set_group_status(self, *, actor: User, group_id: int, status: str) -> AccessGroupDetailOut:
        group = self._get_group_or_404(group_id)
        if status not in {AccessGroupStatus.ACTIVE, AccessGroupStatus.INACTIVE}:
            raise AdminError(f"Unknown group status: {status}")
        if status == AccessGroupStatus.INACTIVE and group.group_type == "SYSTEM":
            raise SystemGroupProtectedError("SYSTEM access groups cannot be deactivated")
        previous = group.status
        group.status = status
        self.db.flush()
        self.audit.log(
            actor_id=actor.id, action="access_group.updated", entity_type="AccessGroup", entity_id=group.id,
            previous_state={"status": previous}, new_state={"status": status},
        )
        self.db.commit()
        return self._to_group_detail_out(group)

    def add_group_member(self, *, actor: User, group_id: int, target_user_id: int) -> AccessGroupDetailOut:
        group = self._get_group_or_404(group_id)
        target = self.db.get(User, target_user_id)
        if target is None:
            raise NotFoundError(f"User {target_user_id} not found")
        existing = self.db.execute(
            select(UserGroupMembership).where(
                UserGroupMembership.access_group_id == group_id, UserGroupMembership.user_id == target_user_id
            )
        ).scalars().first()
        if existing is not None:
            return self._to_group_detail_out(group)
        membership = UserGroupMembership(user_id=target_user_id, access_group_id=group_id)
        self.db.add(membership)
        self.db.flush()
        self.audit.log(
            actor_id=actor.id, action="access_group.member_added", entity_type="UserGroupMembership",
            entity_id=membership.id,
            new_state={"user_id": target_user_id, "access_group_id": group_id},
        )
        self.db.commit()
        return self._to_group_detail_out(group)

    def remove_group_member(self, *, actor: User, group_id: int, target_user_id: int) -> AccessGroupDetailOut:
        group = self._get_group_or_404(group_id)
        membership = self.db.execute(
            select(UserGroupMembership).where(
                UserGroupMembership.access_group_id == group_id, UserGroupMembership.user_id == target_user_id
            )
        ).scalars().first()
        if membership is None:
            raise NotFoundError(f"User {target_user_id} is not a member of group {group_id}")
        membership_id = membership.id
        self.audit.log(
            actor_id=actor.id, action="access_group.member_removed", entity_type="UserGroupMembership",
            entity_id=membership_id,
            previous_state={"user_id": target_user_id, "access_group_id": group_id},
        )
        self.db.delete(membership)
        self.db.commit()
        return self._to_group_detail_out(group)

    def upsert_group_module_assignment(
        self, *, actor: User, group_id: int, module_key: str, role: str, enabled: bool,
        client_scope: ClientScopeIn | None,
    ) -> AccessGroupDetailOut:
        group = self._get_group_or_404(group_id)
        role_row = self.authz.role_display(module_key, role)
        if role_row is None:
            raise AdminError(f"Unknown role '{role}' for module '{module_key}'")
        self._validate_client_scope(client_scope)

        stmt = select(GroupModuleRole).where(
            GroupModuleRole.access_group_id == group_id, GroupModuleRole.module_key == module_key
        )
        group_role = self.db.execute(stmt).scalars().first()
        previous_state = None
        if group_role is None:
            group_role = GroupModuleRole(access_group_id=group_id, module_key=module_key, role=role, enabled=enabled)
            self.db.add(group_role)
            self.db.flush()
        else:
            previous_state = {"role": group_role.role, "enabled": group_role.enabled}
            group_role.role = role
            group_role.enabled = enabled

        if client_scope is not None:
            self.db.execute(
                GroupModuleClientScope.__table__.delete().where(
                    GroupModuleClientScope.group_module_role_id == group_role.id
                )
            )
            if client_scope.all_clients:
                self.db.add(GroupModuleClientScope(group_module_role_id=group_role.id, all_clients=True))
            else:
                for client_id in client_scope.client_ids:
                    self.db.add(
                        GroupModuleClientScope(
                            group_module_role_id=group_role.id, client_id=client_id, all_clients=False
                        )
                    )

        self.db.flush()
        self.audit.log(
            actor_id=actor.id, action="group_module_assignment.upserted", entity_type="AccessGroup",
            entity_id=group_id,
            previous_state=previous_state,
            new_state={
                "module_key": module_key, "role": role, "enabled": enabled,
                "client_scope": (
                    "ALL_CLIENTS" if client_scope and client_scope.all_clients
                    else (client_scope.client_ids if client_scope else None)
                ),
            },
        )
        self.db.commit()
        return self._to_group_detail_out(group)

    def remove_group_module_assignment(self, *, actor: User, group_id: int, module_key: str) -> AccessGroupDetailOut:
        group = self._get_group_or_404(group_id)
        stmt = select(GroupModuleRole).where(
            GroupModuleRole.access_group_id == group_id, GroupModuleRole.module_key == module_key
        )
        group_role = self.db.execute(stmt).scalars().first()
        if group_role is None:
            raise NotFoundError(f"Group {group_id} has no assignment for module '{module_key}'")
        self.audit.log(
            actor_id=actor.id, action="group_module_assignment.removed", entity_type="AccessGroup",
            entity_id=group_id,
            previous_state={"module_key": module_key, "role": group_role.role},
        )
        self.db.delete(group_role)
        self.db.commit()
        return self._to_group_detail_out(group)

    # --- Applications (app-centric admin view) ------------------------------

    def application_detail(self, module_key: str) -> ApplicationDetailOut:
        module = self.db.execute(
            select(ApplicationModule).where(ApplicationModule.key == module_key)
        ).scalars().first()
        if module is None:
            raise NotFoundError(f"Module '{module_key}' not found")

        assigned_users = []
        direct_stmt = select(UserModuleRole).where(UserModuleRole.module_key == module_key)
        for mr in self.db.execute(direct_stmt).scalars().all():
            user = self.db.get(User, mr.user_id)
            if user is None:
                continue
            role_row = self.authz.role_display(module_key, mr.role)
            client_ids = self.authz.client_scope_for(mr)
            assigned_users.append(
                ApplicationAssignedUserOut(
                    user_id=user.id, email=user.email, full_name=user.full_name,
                    role=mr.role, role_name=role_row.name if role_row else mr.role, enabled=mr.enabled,
                    client_scope=ClientScopeOut(
                        all_clients=client_ids is None, client_ids=client_ids or [], client_names=[]
                    ),
                )
            )

        assigned_groups = []
        group_stmt = select(GroupModuleRole).where(GroupModuleRole.module_key == module_key)
        for gr in self.db.execute(group_stmt).scalars().all():
            group = self.db.get(AccessGroup, gr.access_group_id)
            if group is None:
                continue
            role_row = self.authz.role_display(module_key, gr.role)
            client_ids = self._group_client_scope(gr)
            assigned_groups.append(
                ApplicationAssignedGroupOut(
                    group_id=group.id, group_key=group.key, group_name=group.display_name,
                    role=gr.role, role_name=role_row.name if role_row else gr.role, enabled=gr.enabled,
                    client_scope=ClientScopeOut(
                        all_clients=client_ids is None, client_ids=client_ids or [], client_names=[]
                    ),
                )
            )

        return ApplicationDetailOut(
            module_key=module.key, module_name=module.name, description=module.description,
            status=module.status, enabled=module.enabled,
            assigned_users=assigned_users, assigned_groups=assigned_groups,
            direct_user_count=len(assigned_users), group_count=len(assigned_groups),
        )

    # --- Dashboard ----------------------------------------------------------

    def dashboard(self) -> AdminDashboardOut:
        total_users = self.db.execute(select(func.count(User.id))).scalar_one()
        active_users = self.db.execute(select(func.count(User.id)).where(User.is_active.is_(True))).scalar_one()
        platform_admins = self.db.execute(
            select(func.count(User.id)).where(User.platform_role == PlatformRole.PLATFORM_ADMIN.value)
        ).scalar_one()
        super_admins = self.db.execute(
            select(func.count(User.id)).where(User.platform_role == PlatformRole.SUPER_ADMIN.value)
        ).scalar_one()
        active_modules = self.db.execute(
            select(func.count(ApplicationModule.id)).where(ApplicationModule.enabled.is_(True))
        ).scalar_one()
        return AdminDashboardOut(
            total_users=total_users, active_users=active_users, platform_admins=platform_admins,
            super_admins=super_admins, active_modules=active_modules,
            # talent-api owns TalentRequest; admin-api fills this in for real
            # after calling GET /api/talent/summary.
            pending_talent_requests=0,
        )
