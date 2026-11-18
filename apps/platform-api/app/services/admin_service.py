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

Client names: `platform-api` has owned the canonical `Client`/
`ClientExternalId` tables since Architecture Completion Plan Wave A
(§6.1) — this service resolves client names directly from its own
database, no cross-service call needed (the pre-Wave-A `talent-api`
`/clients-lite` dependency this docstring used to describe was deleted).
The live **pending-talent-request count** is still not this service's to
know — `talent_requests` remains talent-api-owned operational data — so
that field is always returned as `0` here; `admin-api` enriches it
separately by calling talent-api's `/api/talent/summary` and merging
before responding to the browser, so the public `/api/admin/*` contract
app-web/admin-web sees is unchanged. See
``docs/platform/service-contracts.md``, ``docs/platform/data-ownership.md``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import MODULE_BIRTHDAY, MODULE_SPARK, MODULE_TALENT_FLOW, PlatformRole
from app.core.permissions import APPOINTMENT_ONLY_ROLES
from app.models.access_group import (
    AccessGroup,
    AccessGroupStatus,
    GroupModuleClientScope,
    GroupModuleRole,
    UserGroupMembership,
)
from app.models.client import Client, ClientExternalId
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
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
    ClientOut,
    ClientScopeIn,
    ClientScopeOut,
    EffectiveAccessOut,
    EffectiveModuleAccessOut,
    GroupMemberOut,
    GroupModuleAssignmentOut,
    ModuleAssignmentOut,
)
from app.services import protected_admin
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthorizationService
from app.services.notification_service import NotificationService

ADMIN_PLATFORM_ROLES = {PlatformRole.SUPER_ADMIN.value, PlatformRole.PLATFORM_ADMIN.value}
BREAK_GLASS_MIN_REASON = 10

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


class ConflictError(AdminError):
    """The request collides with an existing record (HTTP 409)."""


class LastSuperAdminError(ForbiddenError):
    pass


class ProtectedAdminForbiddenError(ForbiddenError):
    """The target is a protected administrator (see app/services/protected_admin.py)."""


class SystemGroupProtectedError(ForbiddenError):
    """SYSTEM access groups cannot be deleted or deactivated (mirrors the
    LastSuperAdminError guard-rail pattern above)."""


class AdminService:
    def __init__(self, db: Session):
        self.db = db
        self.authz = AuthorizationService(db)
        self.audit = AuditService(db)

    def _resolve_client_scope_refs(self, client_scope: ClientScopeIn | None) -> dict[int, str]:
        """Resolve each concrete client id in a module/group scope to its
        durable ``Client.public_id`` (Architecture Completion Plan §6.1) —
        a purely local check against the platform-owned ``clients`` table.

        A submitted id is accepted if it matches a platform ``Client.id``
        directly, or the ``talent-api`` legacy integer id recorded in
        ``client_external_ids`` (so the Admin Center's existing picker keeps
        working through the transition). Any id that resolves to neither is
        an ``AdminError`` (400). Returns ``{submitted_id: public_id}``; empty
        for an all-clients / empty scope."""
        if client_scope is None or client_scope.all_clients or not client_scope.client_ids:
            return {}

        wanted = [int(c) for c in client_scope.client_ids]
        resolved: dict[int, str] = {}

        by_pk = {
            row.id: row.public_id
            for row in self.db.execute(
                select(Client).where(Client.id.in_(wanted))
            ).scalars()
        }
        legacy_rows = self.db.execute(
            select(ClientExternalId).where(
                ClientExternalId.provider == "talent-api",
                ClientExternalId.external_id.in_([str(c) for c in wanted]),
            )
        ).scalars()
        by_legacy = {int(r.external_id): r.client_id for r in legacy_rows}
        pk_to_public = {
            row.id: row.public_id
            for row in self.db.execute(select(Client)).scalars()
        }

        unknown: list[int] = []
        for cid in wanted:
            if cid in by_pk:
                resolved[cid] = by_pk[cid]
            elif cid in by_legacy and by_legacy[cid] in pk_to_public:
                resolved[cid] = pk_to_public[by_legacy[cid]]
            else:
                unknown.append(cid)
        if unknown:
            raise AdminError(f"Unknown client id(s): {sorted(unknown)}")
        return resolved

    # --- Clients (platform-owned canonical identity, §6.1) --------------

    def _client_scope_out(self, client_ids: list[int] | None) -> ClientScopeOut:
        """Build a client-scope DTO, resolving display names locally — the
        canonical Client table is platform-owned now, so admin-api no longer
        enriches names from talent-api (§6.1). ``client_ids`` are still the
        legacy talent-api integers the Admin Center picker uses; names come
        via the ``client_external_ids`` crosswalk."""
        ids = client_ids or []
        names: dict[int, str] = {}
        if ids:
            rows = self.db.execute(
                select(ClientExternalId.external_id, Client.name)
                .join(Client, Client.id == ClientExternalId.client_id)
                .where(
                    ClientExternalId.provider == "talent-api",
                    ClientExternalId.external_id.in_([str(i) for i in ids]),
                )
            ).all()
            names = {int(ext): name for ext, name in rows}
        return ClientScopeOut(
            all_clients=client_ids is None,
            client_ids=ids,
            client_names=[names.get(cid, str(cid)) for cid in ids],
        )

    def list_clients(self) -> list[ClientOut]:
        rows = self.db.execute(select(Client).order_by(Client.name)).scalars().all()
        return [
            ClientOut(
                id=c.id, public_id=c.public_id, name=c.name, status=c.status,
                created_at=c.created_at,
            )
            for c in rows
        ]

    def create_client(self, *, actor: User, name: str, status: str = "ACTIVE") -> ClientOut:
        name = name.strip()
        if not name:
            raise AdminError("Client name is required")
        if self.db.execute(select(Client).where(Client.name == name)).scalars().first():
            raise AdminError(f"A client named '{name}' already exists")
        client = Client(public_id=f"cli-{uuid.uuid4().hex[:12]}", name=name, status=status)
        self.db.add(client)
        self.db.flush()
        self.audit.log(
            actor_id=actor.id, action="client.created", entity_type="Client", entity_id=client.id,
            new_state={"public_id": client.public_id, "name": name, "status": status},
        )
        self.db.commit()
        return ClientOut(
            id=client.id, public_id=client.public_id, name=client.name, status=client.status,
            created_at=client.created_at,
        )

    # --- Users -----------------------------------------------------------

    def _module_names(self) -> dict[str, str]:
        rows = self.db.execute(select(ApplicationModule.key, ApplicationModule.name)).all()
        return dict(rows)

    def _to_module_assignment_out(
        self, module_role: UserModuleRole, module_names: dict[str, str]
    ) -> ModuleAssignmentOut:
        role_row = self.authz.role_display(module_role.module_key, module_role.role)
        client_ids = self.authz.client_scope_for(module_role)
        return ModuleAssignmentOut(
            module_key=module_role.module_key,
            module_name=module_names.get(module_role.module_key, module_role.module_key),
            role=module_role.role,
            role_name=role_row.name if role_row else module_role.role,
            enabled=module_role.enabled,
            client_scope=self._client_scope_out(client_ids),
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
            protected=protected_admin.is_protected_user(self.db, user),
            employee_number=user.employee_number,
            directory_verified=self.authz.identity_verified(user),
            verification_source=(
                ("DIRECTORY" if user.directory_verified_at else "SIGN_IN") if self.authz.identity_verified(user) else "NONE"
            ),
            employee_record=user.employee_record_status,
            eligible_employee=self.authz.is_eligible_employee(user),
            signed_in=user.last_login_at is not None,
        )

    def list_users(self) -> list[AdminUserOut]:
        users = list(self.db.execute(select(User).order_by(User.full_name)).scalars().all())
        return [self.to_user_out(u) for u in users]

    def get_user(self, user_id: int) -> AdminUserOut:
        user = self.db.get(User, user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return self.to_user_out(user)

    def create_user(self, *, actor: User, email: str, full_name: str, title: str | None = None) -> AdminUserOut:
        """Pre-provision an internal employee who has not signed in yet, so access
        can be assigned in advance. The account holds no credentials: it is linked
        to a Microsoft identity at the first verified Entra sign-in with this email
        (see ``entra_service.resolve_entra_user``)."""
        email = email.strip().lower()
        full_name = full_name.strip()
        title = (title or "").strip() or None
        local, _, domain = email.rpartition("@")
        if not local or "." not in domain or any(c.isspace() for c in email) or email.count("@") != 1:
            raise AdminError("Enter a valid email address.")
        if not full_name:
            raise AdminError("Full name is required.")
        allowed = {d.strip().lower() for d in get_settings().entra_internal_email_domains.split(",") if d.strip()}
        if not allowed:
            raise AdminError("Users cannot be added here: no internal email domain is configured for this environment.")
        if domain not in allowed:
            raise AdminError(f"Only internal email addresses can be added ({', '.join(sorted(allowed))}).")
        if self.db.execute(select(User.id).where(func.lower(User.email) == email)).first() is not None:
            raise ConflictError(f"A user with the email {email} already exists.")

        user = User(
            email=email, full_name=full_name, title=title,
            platform_role=PlatformRole.PLATFORM_USER.value, identity_provider="ENTRA", is_active=True,
        )
        self.db.add(user)
        self.db.flush()
        self.audit.log(
            actor_id=actor.id, action="user.created", entity_type="User", entity_id=user.id,
            new_state={"email": email, "full_name": full_name, "platform_role": user.platform_role, "is_active": True},
            subject_user_id=user.id,
        )
        self.db.commit()
        return self.to_user_out(user)

    def _active_super_admin_count(self, *, excluding_user_id: int | None = None) -> int:
        stmt = select(func.count(User.id)).where(
            User.platform_role == PlatformRole.SUPER_ADMIN.value, User.is_active.is_(True)
        )
        if excluding_user_id is not None:
            stmt = stmt.where(User.id != excluding_user_id)
        return self.db.execute(stmt).scalar_one()

    def _refuse_protected(self, *, actor: User, target: User, attempted: dict, **checks) -> None:
        """Refuse an action aimed at a protected administrator. The refusal is recorded in the audit
        log (committed on its own; nothing else was changed) and then raised as a 403."""
        try:
            protected_admin.assert_may_change(self.db, target, **checks)
        except protected_admin.ProtectedAdminError as exc:
            self.db.rollback()
            self.audit.log(
                actor_id=actor.id, action="protected_admin.change_blocked", entity_type="User", entity_id=target.id,
                new_state=attempted, metadata={"reason": str(exc)}, subject_user_id=target.id,
            )
            self.db.commit()
            raise ProtectedAdminForbiddenError(str(exc)) from exc

    # --- Guards on who may change whose access ---------------------------------

    def can_manage_admins(self, actor: User) -> bool:
        return "platform.admin.manage_admins" in self.authz.platform_permissions(actor)

    def guard_access_change(
        self, *, actor: User, target: User, break_glass_reason: str | None = None
    ) -> dict | None:
        """Refuse a change to the actor's own access, and a change to an administrator's access by
        anyone who may not manage administrators. A Super Admin may change their own access only
        as a break-glass action with a written reason; the returned metadata marks the audit entry
        and ``notify_break_glass`` tells the other Super Admins. Returns None for an ordinary change."""
        if actor.id == target.id:
            reason = (break_glass_reason or "").strip()
            if self.can_manage_admins(actor) and len(reason) >= BREAK_GLASS_MIN_REASON:
                return {"break_glass": True, "break_glass_reason": reason}
            raise ForbiddenError(
                "You cannot change your own access. Ask another administrator"
                + (
                    f", or use break-glass with a reason of at least {BREAK_GLASS_MIN_REASON} characters."
                    if self.can_manage_admins(actor)
                    else "."
                )
            )
        if target.platform_role in ADMIN_PLATFORM_ROLES and not self.can_manage_admins(actor):
            raise ForbiddenError("Only a Super Admin may change an administrator's access.")
        return None

    def notify_break_glass(self, *, actor: User, summary: str) -> None:
        """Tell every other active Super Admin (best effort, inside the caller's transaction)."""
        others = self.db.execute(
            select(User.id).where(
                User.platform_role == PlatformRole.SUPER_ADMIN.value, User.is_active.is_(True), User.id != actor.id
            )
        ).scalars().all()
        for user_id in others:
            NotificationService(self.db).notify_user(
                user_id=user_id, type="ACCESS_BREAK_GLASS",
                title=f"Break-glass access change by {actor.full_name}",
                body=summary, related_entity_type="User", related_entity_id=actor.id,
            )

    @staticmethod
    def _audit_meta(channel: str, break_glass: dict | None, **extra) -> dict:
        meta = {"channel": channel, **extra}
        if break_glass:
            meta.update(break_glass)
        return meta

    def set_user_active(self, *, actor: User, target_user_id: int, is_active: bool) -> AdminUserOut:
        target = self.db.get(User, target_user_id)
        if target is None:
            raise NotFoundError(f"User {target_user_id} not found")
        if target.platform_role in ADMIN_PLATFORM_ROLES and not self.can_manage_admins(actor):
            raise ForbiddenError("Only a Super Admin may activate or deactivate an administrator.")
        if not is_active:
            self._refuse_protected(actor=actor, target=target, attempted={"is_active": False}, deactivate=True)

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
            subject_user_id=target.id,
        )
        self.db.commit()
        return self.to_user_out(target)

    def set_platform_role(self, *, actor: User, target_user_id: int, new_role: str) -> AdminUserOut:
        target = self.db.get(User, target_user_id)
        if target is None:
            raise NotFoundError(f"User {target_user_id} not found")
        if new_role not in {r.value for r in PlatformRole}:
            raise AdminError(f"Unknown platform role: {new_role}")
        self._refuse_protected(actor=actor, target=target, attempted={"platform_role": new_role}, new_role=new_role)

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
            subject_user_id=target.id,
        )
        self.db.commit()
        return self.to_user_out(target)

    # --- Module assignments ------------------------------------------------

    def _effective_client_scope(self, module_key: str, client_scope: ClientScopeIn | None) -> ClientScopeIn | None:
        """Modules that don't read client scope ignore whatever is submitted
        and store the neutral "all clients" scope (unrestricted), replacing
        any specific client rows saved before the capability flag existed."""
        module = self.db.execute(
            select(ApplicationModule).where(ApplicationModule.key == module_key)
        ).scalars().first()
        if module is not None and not module.supports_client_scope:
            return ClientScopeIn(all_clients=True, client_ids=[])
        return client_scope

    def _flush_new_assignment(self) -> None:
        """Insert a first assignment. The unique constraint decides when two
        requests race to create it, so neither can leave a second row behind."""
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("This access was just saved by another request. Reload and try again.") from exc

    @staticmethod
    def _require_explicit_client_scope(client_scope: ClientScopeIn | None, *, is_new: bool) -> None:
        """An assignment with no scope rows resolves as unrestricted, so a scope
        that names no client must never be stored as if it restricted anything."""
        if client_scope is None:
            if is_new:
                raise AdminError("Client scope is required: choose All Clients or select at least one client.")
            return
        if not client_scope.all_clients and not client_scope.client_ids:
            raise AdminError("Select at least one client, or choose All Clients.")

    def upsert_module_assignment(
        self,
        *,
        actor: User,
        target_user_id: int,
        module_key: str,
        role: str,
        enabled: bool,
        client_scope: ClientScopeIn | None,
        channel: str = "CENTRAL",
        break_glass_reason: str | None = None,
        extra_audit: dict | None = None,
    ) -> AdminUserOut:
        target = self.db.get(User, target_user_id)
        if target is None:
            raise NotFoundError(f"User {target_user_id} not found")

        role_row = self.authz.role_display(module_key, role)
        if role_row is None:
            raise AdminError(f"Unknown role '{role}' for module '{module_key}'")
        if (module_key, role) in APPOINTMENT_ONLY_ROLES:
            raise AdminError("This role is granted only by appointing an Application Administrator.")
        break_glass = self.guard_access_change(actor=actor, target=target, break_glass_reason=break_glass_reason)
        client_scope = self._effective_client_scope(module_key, client_scope)
        ref_map = self._resolve_client_scope_refs(client_scope)

        stmt = select(UserModuleRole).where(
            UserModuleRole.user_id == target_user_id, UserModuleRole.module_key == module_key
        )
        module_role = self.db.execute(stmt).scalars().first()
        self._require_explicit_client_scope(client_scope, is_new=module_role is None)
        previous_state = None
        if module_role is None:
            module_role = UserModuleRole(user_id=target_user_id, module_key=module_key, role=role, enabled=enabled)
            self.db.add(module_role)
            self._flush_new_assignment()
            action = "module_assignment.created"
        else:
            previous_state = {"role": module_role.role, "enabled": module_role.enabled}
            module_role.role = role
            module_role.enabled = enabled
            action = "module_assignment.updated"

        # TALENT_CLIENT keeps its legacy single-tenant client_id/client_ref in
        # sync for code paths that still read it (dropped after the transition).
        if client_scope is not None:
            if not client_scope.all_clients and len(client_scope.client_ids) == 1:
                only = int(client_scope.client_ids[0])
                module_role.client_id = only
                module_role.client_ref = ref_map.get(only)
            else:
                module_role.client_id = None
                module_role.client_ref = None

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
                            user_module_role_id=module_role.id,
                            client_id=client_id,
                            client_ref=ref_map.get(int(client_id)),
                            all_clients=False,
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
            metadata=self._audit_meta(channel, break_glass, module_key=module_key, **(extra_audit or {})),
            subject_user_id=target_user_id,
        )
        if break_glass:
            self.notify_break_glass(actor=actor, summary=f"{module_key}: own role set to {role}. Reason: "
                                    f"{break_glass['break_glass_reason']}")
        self.db.commit()
        return self.to_user_out(target)

    def remove_module_assignment(
        self, *, actor: User, target_user_id: int, module_key: str, channel: str = "CENTRAL",
        break_glass_reason: str | None = None,
    ) -> AdminUserOut:
        """Remove a user's own (direct) assignment to an application.

        Default employee access is always on for an eligible employee: it has no row to delete and
        cannot be removed here. Deleting a direct assignment never touches it, so a person whose
        higher role is removed keeps the standard role."""
        target = self.db.get(User, target_user_id)
        if target is None:
            raise NotFoundError(f"User {target_user_id} not found")
        stmt = select(UserModuleRole).where(
            UserModuleRole.user_id == target_user_id, UserModuleRole.module_key == module_key
        )
        module_role = self.db.execute(stmt).scalars().first()

        if module_role is None:
            if self.authz.baseline_roles(target).get(module_key) is not None:
                raise ConflictError(
                    "This application's standard access is included for every eligible employee and cannot be removed."
                )
            raise NotFoundError(f"User {target_user_id} has no assignment for module '{module_key}'")
        break_glass = self.guard_access_change(actor=actor, target=target, break_glass_reason=break_glass_reason)

        self.audit.log(
            actor_id=actor.id,
            action="module_assignment.removed",
            entity_type="UserModuleRole",
            entity_id=module_role.id,
            previous_state={"user_id": target_user_id, "module_key": module_key, "role": module_role.role},
            metadata=self._audit_meta(channel, break_glass, module_key=module_key),
            subject_user_id=target_user_id,
        )
        if break_glass:
            self.notify_break_glass(actor=actor, summary=f"{module_key}: own assignment removed. Reason: "
                                    f"{break_glass['break_glass_reason']}")
        self.db.delete(module_role)
        self.db.commit()
        return self.to_user_out(target)

    def _default_role(self, module_key: str) -> str | None:
        """The role every eligible internal employee holds in this application, if any."""
        return self.db.execute(
            select(ModuleBaselineRole.role).where(
                ModuleBaselineRole.module_key == module_key, ModuleBaselineRole.enabled.is_(True)
            )
        ).scalar_one_or_none()

    def restore_default_access(self, *, actor: User, target_user_id: int, module_key: str) -> AdminUserOut:
        """Kept for compatibility. Default access is always on, so this only clears a leftover
        exclusion row (one that predates always-on access), if any; otherwise it changes nothing."""
        target = self.db.get(User, target_user_id)
        if target is None:
            raise NotFoundError(f"User {target_user_id} not found")
        default_role = self._default_role(module_key)
        exclusion = self.db.execute(
            select(UserModuleRole).where(
                UserModuleRole.user_id == target_user_id, UserModuleRole.module_key == module_key,
                UserModuleRole.enabled.is_(False), UserModuleRole.role == default_role,
            )
        ).scalars().first()
        if default_role is None or exclusion is None:
            return self.to_user_out(target)
        self.audit.log(
            actor_id=actor.id, action="module_assignment.default_access_restored", entity_type="UserModuleRole",
            entity_id=exclusion.id, previous_state={"user_id": target_user_id, "module_key": module_key, "enabled": False},
            new_state={"module_key": module_key, "role": default_role, "source": "DEFAULT"},
            subject_user_id=target_user_id,
        )
        self.db.delete(exclusion)
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
                user_count=counts.get(m.key, 0), supports_client_scope=m.supports_client_scope,
            )
            for m in modules
        ]

    def set_module_enabled(self, *, actor: User, module_key: str, enabled: bool) -> AdminModuleOut:
        """Enable or disable an application in the registry. The access-version listener raises
        every user's version in the same transaction, so every session issued with the old setting
        is refused by the applications and refreshed without (or with) the application."""
        module = self.db.execute(select(ApplicationModule).where(ApplicationModule.key == module_key)).scalars().first()
        if module is None:
            raise NotFoundError(f"Module '{module_key}' not found")
        previous = module.enabled
        if previous != enabled:
            module.enabled = enabled
            self.db.flush()
            self.audit.log(
                actor_id=actor.id, action="module.enabled" if enabled else "module.disabled",
                entity_type="ApplicationModule", entity_id=module.id,
                previous_state={"enabled": previous}, new_state={"enabled": enabled},
                metadata={"channel": "CENTRAL", "module_key": module_key},
            )
            self.db.commit()
        return next(m for m in self.list_modules() if m.key == module_key)

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
                    appointment_only=(r.module_key, r.key) in APPOINTMENT_ONLY_ROLES,
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

    def list_audit(
        self, *, limit: int = 200, entity_type: str | None = None, entity_id: int | None = None,
        user_id: int | None = None,
    ) -> list[AuditLogOut]:
        """Newest first. ``user_id`` lists everything recorded about one person:
        their account, application assignments and group memberships."""
        from app.models.audit_log import AuditLog

        stmt = select(AuditLog)
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        if user_id is not None:
            stmt = stmt.where(AuditLog.subject_user_id == user_id)
        stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
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
                AccessSourceOut(
                    type=g.source_type, role=g.role, group_id=g.group_id, group_name=g.source_name, mandated=g.mandated
                )
                for g in grants
            ]
            modules_out.append(
                EffectiveModuleAccessOut(
                    module_key=module_key,
                    module_name=module_names.get(module_key, module_key),
                    enabled=enabled,
                    role=primary.role,
                    role_name=role_row.name if role_row else primary.role,
                    client_scope=self._client_scope_out(client_ids),
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
            default_access_excluded=[key for key, _role in self.authz.baseline_exclusions(user)],
            suspended_modules=sorted(self.authz.suspended_modules(user)),
            administered_modules=sorted(a.module_key for a in self.authz.appointments(user)),
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
                    client_scope=self._client_scope_out(client_ids),
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

    def _guard_group_change(self, *, actor: User, group_id: int, break_glass_reason: str | None) -> dict | None:
        """A change to a group's grants changes every member's access: refused when the actor is a
        member (their own access; Super Admin break-glass only) or, for anyone who may not manage
        administrators, when an administrator is a member."""
        members = self.db.execute(
            select(User).join(UserGroupMembership, UserGroupMembership.user_id == User.id)
            .where(UserGroupMembership.access_group_id == group_id)
        ).scalars().all()
        break_glass = None
        for member in members:
            if member.id == actor.id:
                break_glass = self.guard_access_change(actor=actor, target=member, break_glass_reason=break_glass_reason)
        if not self.can_manage_admins(actor) and any(m.platform_role in ADMIN_PLATFORM_ROLES for m in members):
            raise ForbiddenError("Only a Super Admin may change a group that has administrators as members.")
        return break_glass

    def add_group_member(
        self, *, actor: User, group_id: int, target_user_id: int, break_glass_reason: str | None = None
    ) -> AccessGroupDetailOut:
        group = self._get_group_or_404(group_id)
        target = self.db.get(User, target_user_id)
        if target is None:
            raise NotFoundError(f"User {target_user_id} not found")
        break_glass = self.guard_access_change(actor=actor, target=target, break_glass_reason=break_glass_reason)
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
            metadata=self._audit_meta("CENTRAL", break_glass),
            subject_user_id=target_user_id,
        )
        if break_glass:
            self.notify_break_glass(actor=actor, summary=f"Added self to group {group.display_name}. Reason: "
                                    f"{break_glass['break_glass_reason']}")
        self.db.commit()
        return self._to_group_detail_out(group)

    def remove_group_member(
        self, *, actor: User, group_id: int, target_user_id: int, break_glass_reason: str | None = None
    ) -> AccessGroupDetailOut:
        group = self._get_group_or_404(group_id)
        target = self.db.get(User, target_user_id)
        if target is not None:
            self.guard_access_change(actor=actor, target=target, break_glass_reason=break_glass_reason)
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
            subject_user_id=target_user_id,
        )
        self.db.delete(membership)
        self.db.commit()
        return self._to_group_detail_out(group)

    def upsert_group_module_assignment(
        self, *, actor: User, group_id: int, module_key: str, role: str, enabled: bool,
        client_scope: ClientScopeIn | None, break_glass_reason: str | None = None,
    ) -> AccessGroupDetailOut:
        group = self._get_group_or_404(group_id)
        role_row = self.authz.role_display(module_key, role)
        if role_row is None:
            raise AdminError(f"Unknown role '{role}' for module '{module_key}'")
        if (module_key, role) in APPOINTMENT_ONLY_ROLES:
            raise AdminError("This role is granted only by appointing an Application Administrator.")
        self._guard_group_change(actor=actor, group_id=group_id, break_glass_reason=break_glass_reason)
        client_scope = self._effective_client_scope(module_key, client_scope)
        ref_map = self._resolve_client_scope_refs(client_scope)

        stmt = select(GroupModuleRole).where(
            GroupModuleRole.access_group_id == group_id, GroupModuleRole.module_key == module_key
        )
        group_role = self.db.execute(stmt).scalars().first()
        self._require_explicit_client_scope(client_scope, is_new=group_role is None)
        previous_state = None
        if group_role is None:
            group_role = GroupModuleRole(access_group_id=group_id, module_key=module_key, role=role, enabled=enabled)
            self.db.add(group_role)
            self._flush_new_assignment()
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
                            group_module_role_id=group_role.id,
                            client_id=client_id,
                            client_ref=ref_map.get(int(client_id)),
                            all_clients=False,
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

    def remove_group_module_assignment(
        self, *, actor: User, group_id: int, module_key: str, break_glass_reason: str | None = None
    ) -> AccessGroupDetailOut:
        group = self._get_group_or_404(group_id)
        self._guard_group_change(actor=actor, group_id=group_id, break_glass_reason=break_glass_reason)
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
                    client_scope=self._client_scope_out(client_ids),
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
                    client_scope=self._client_scope_out(client_ids),
                )
            )

        return ApplicationDetailOut(
            module_key=module.key, module_name=module.name, description=module.description,
            status=module.status, enabled=module.enabled,
            assigned_users=assigned_users, assigned_groups=assigned_groups,
            direct_user_count=len(assigned_users), group_count=len(assigned_groups),
            supports_client_scope=module.supports_client_scope,
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
