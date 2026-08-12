"""DijiOne Admin Center service (Phase 2 CR §11-31).

Every mutation here is audit-logged (CR §35) and every SUPER_ADMIN-affecting
change is checked against the lockout rule (CR §50): the last active
SUPER_ADMIN can never be deactivated or demoted, and a caller without
``platform.admin.manage_admins`` can never grant or revoke SUPER_ADMIN /
PLATFORM_ADMIN (CR §12 — PLATFORM_ADMIN must not alter administrators).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import MODULE_BIRTHDAY, MODULE_SPARK, MODULE_TALENT_FLOW, PlatformRole
from app.models.client import Client
from app.models.module import ApplicationModule
from app.models.role import Permission, Role, RolePermission
from app.models.talent_request import TalentRequest
from app.models.user import User, UserModuleRole
from app.models.user_module_client_scope import UserModuleClientScope
from app.schemas.admin import (
    AdminDashboardOut,
    AdminModuleOut,
    AdminPermissionOut,
    AdminRoleOut,
    AdminUserOut,
    AuditLogOut,
    ClientScopeIn,
    ClientScopeOut,
    EffectiveAccessOut,
    EffectiveModuleAccessOut,
    ModuleAssignmentOut,
)
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthorizationService

ADMIN_PLATFORM_ROLES = {PlatformRole.SUPER_ADMIN.value, PlatformRole.PLATFORM_ADMIN.value}

_MODULE_DISPLAY_ORDER = [MODULE_TALENT_FLOW, MODULE_BIRTHDAY, MODULE_SPARK]


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


class AdminService:
    def __init__(self, db: Session):
        self.db = db
        self.authz = AuthorizationService(db)
        self.audit = AuditService(db)

    # --- Users -----------------------------------------------------------

    def _module_names(self) -> dict[str, str]:
        rows = self.db.execute(select(ApplicationModule.key, ApplicationModule.name)).all()
        return dict(rows)

    def _client_names(self, client_ids: list[int]) -> dict[int, str]:
        if not client_ids:
            return {}
        rows = self.db.execute(
            select(Client.id, Client.name).where(Client.id.in_(client_ids))
        ).all()
        return dict(rows)

    def _to_module_assignment_out(
        self, module_role: UserModuleRole, module_names: dict[str, str]
    ) -> ModuleAssignmentOut:
        role_row = self.authz.role_display(module_role.module_key, module_role.role)
        client_ids = self.authz.client_scope_for(module_role)
        all_clients = client_ids is None
        names = self._client_names(client_ids) if client_ids else {}
        return ModuleAssignmentOut(
            module_key=module_role.module_key,
            module_name=module_names.get(module_role.module_key, module_role.module_key),
            role=module_role.role,
            role_name=role_row.name if role_row else module_role.role,
            enabled=module_role.enabled,
            client_scope=ClientScopeOut(
                all_clients=all_clients,
                client_ids=client_ids or [],
                client_names=[names.get(cid, str(cid)) for cid in (client_ids or [])],
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

    def list_clients(self) -> list[dict]:
        """Lightweight client listing for the Admin Center's client-scope
        picker — administrators may not hold a DijiTalentFlow module role
        themselves, so they cannot use ``/api/talent/clients``."""
        rows = self.db.execute(select(Client.id, Client.name).order_by(Client.name)).all()
        return [{"id": cid, "name": name} for cid, name in rows]

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
        stmt = select(UserModuleRole).where(UserModuleRole.user_id == user_id)
        module_roles = list(self.db.execute(stmt).scalars().all())

        modules_out = []
        for mr in module_roles:
            role_row = self.authz.role_display(mr.module_key, mr.role)
            permissions = sorted(self.authz.module_role_permissions(mr))
            client_ids = self.authz.client_scope_for(mr)
            names = self._client_names(client_ids) if client_ids else {}
            modules_out.append(
                EffectiveModuleAccessOut(
                    module_key=mr.module_key,
                    module_name=module_names.get(mr.module_key, mr.module_key),
                    enabled=mr.enabled,
                    role=mr.role,
                    role_name=role_row.name if role_row else mr.role,
                    client_scope=ClientScopeOut(
                        all_clients=client_ids is None,
                        client_ids=client_ids or [],
                        client_names=[names.get(cid, str(cid)) for cid in (client_ids or [])],
                    ),
                    permissions=permissions,
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

    # --- Dashboard ----------------------------------------------------------

    def dashboard(self) -> AdminDashboardOut:
        from app.core.constants import TalentRequestLifecycleStatus

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
        pending_requests = self.db.execute(
            select(func.count(TalentRequest.id)).where(
                TalentRequest.lifecycle_status == TalentRequestLifecycleStatus.PENDING_REVIEW.value
            )
        ).scalar_one()
        return AdminDashboardOut(
            total_users=total_users, active_users=active_users, platform_admins=platform_admins,
            super_admins=super_admins, active_modules=active_modules, pending_talent_requests=pending_requests,
        )
