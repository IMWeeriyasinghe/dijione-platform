"""Delegated application access administration.

A Super Admin appoints an employee as an access administrator of one application, with explicit
authority (which employee roles they may grant; for client-scoped applications, which clients).
That administrator then manages employee access to that application only, from the application's
own Management → Access page, through ``/api/access/{app}``. The assignments themselves stay in
Platform Core (one source of truth, the same tables Central Admin edits), so session tokens,
revocation, audit and every application's enforcement work exactly as for central changes.

Every rule is checked here, against the database, on every request (never against the token):

* the caller holds an appointment for this application, is an eligible employee, is not
  suspended in it, and the application is enabled;
* the target is an eligible employee (or a directory employee matched to BambooHR, added at that
  moment), is not the caller, not a platform administrator, not a protected account and not an
  administrator of the same application;
* a granted role is in the appointment's ``grantable_roles`` (a subset of the application's
  delegable roles); a granted client scope is within its ``client_authority``;
* an existing assignment or group grant outside that authority is read-only here.

Removing access deletes the direct assignment and, if ordinary group grants would still give
access, records an application suspension (an application-scoped deny). Mandatory access (default
employee access, SYSTEM groups) is never removed. See AuthorizationService for the precedence.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import DELEGATION, DelegationDef
from app.integrations.directory import DirectoryUnavailable
from app.models.access_group import AccessGroup, AccessGroupStatus, GroupModuleRole, UserGroupMembership
from app.models.application_access import ApplicationAccessSuspension, ApplicationAdministrator
from app.models.client import Client
from app.models.module import ApplicationModule
from app.models.user import User, UserModuleRole
from app.schemas.admin import ClientScopeIn
from app.schemas.app_access import (
    AccessClientOut,
    AccessMeOut,
    AccessRoleOut,
    AccessScopeOut,
    AccessSourceOut,
    AdministratorOut,
    AppointIn,
    AppointmentInfoOut,
    AppUserOut,
    AppUsersOut,
    PeopleOut,
    PersonOut,
    RevokePreviewOut,
    SuspensionOut,
)
from app.services import protected_admin
from app.services.admin_service import (
    ADMIN_PLATFORM_ROLES,
    AdminError,
    AdminService,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.services.audit_service import AuditService
from app.services.authorization_service import SYSTEM_GROUP_TYPE, AuthorizationService
from app.services.directory_service import DirectoryService

APPLICATION = "APPLICATION"
CENTRAL = "CENTRAL"
SEARCH_LIMIT = 15


class FeatureDisabled(NotFoundError):
    """Delegated access administration is switched off in this environment."""


@dataclass(frozen=True)
class ImpliedAppointment:
    """An unsaved, request-scoped appointment implied by an ordinary role grant
    (``DelegationDef.implied_by``). Never persisted, never appoints administrators,
    no client authority; recomputed on every request so demotion takes effect at once."""

    user_id: int
    module_key: str
    grantable_roles: list
    client_authority: list | None = None
    can_appoint_admins: bool = False
    appointed_by_user_id: int | None = None
    created_at: object = None
    implied: bool = True


@dataclass
class _Ctx:
    module: ApplicationModule
    definition: DelegationDef
    appointment: ApplicationAdministrator | ImpliedAppointment


class DelegatedAccessService:
    def __init__(self, db: Session):
        self.db = db
        self.authz = AuthorizationService(db)
        self.admin = AdminService(db)
        self.audit = AuditService(db)

    # --- switches, applications, appointments -----------------------------------------

    @staticmethod
    def require_feature() -> None:
        if not get_settings().delegated_access_enabled:
            raise FeatureDisabled("Application access management is not enabled in this environment.")

    def _module(self, module_key: str, *, require_enabled: bool = True) -> tuple[ApplicationModule, DelegationDef]:
        definition = DELEGATION.get(module_key)
        module = self.db.execute(select(ApplicationModule).where(ApplicationModule.key == module_key)).scalars().first()
        if definition is None or module is None:
            raise NotFoundError("This application does not support delegated access administration.")
        if require_enabled and not module.enabled:
            raise ForbiddenError(f"{module.name} is disabled.")
        return module, definition

    def appointment(self, user_id: int, module_key: str) -> ApplicationAdministrator | None:
        return self.db.execute(
            select(ApplicationAdministrator).where(
                ApplicationAdministrator.user_id == user_id, ApplicationAdministrator.module_key == module_key
            )
        ).scalars().first()

    def _suspension(self, user_id: int, module_key: str) -> ApplicationAccessSuspension | None:
        return self.db.execute(
            select(ApplicationAccessSuspension).where(
                ApplicationAccessSuspension.user_id == user_id, ApplicationAccessSuspension.module_key == module_key
            )
        ).scalars().first()

    def _active_appointment(
        self, actor: User, module_key: str
    ) -> ApplicationAdministrator | ImpliedAppointment | None:
        """The caller's appointment for this application: a saved appointment row (always
        preferred), else an implied one (``DelegationDef.implied_by``), else None."""
        if not self.authz.is_eligible_employee(actor) or self._suspension(actor.id, module_key) is not None:
            return None
        appointment = self.appointment(actor.id, module_key)
        if appointment is not None:
            return appointment
        roles = self.authz.implied_appointment_roles(actor, module_key)
        return ImpliedAppointment(user_id=actor.id, module_key=module_key, grantable_roles=roles) if roles else None

    def _holds_implying_role(self, definition: DelegationDef, user: User) -> bool:
        implying = {role for role, _grantable in definition.implied_by}
        if not implying:
            return False
        grants = self.authz.effective_module_roles(user).get(definition.module_key, [])
        return any(g.role in implying for g in grants)

    def _require_admin(self, actor: User, module_key: str) -> _Ctx:
        self.require_feature()
        module, definition = self._module(module_key)
        appointment = self._active_appointment(actor, module_key)
        if appointment is None:
            raise ForbiddenError(f"You are not an access administrator of {module.name}.")
        return _Ctx(module, definition, appointment)

    # --- presentation helpers -----------------------------------------------------------

    def _role_out(self, module_key: str, role: str) -> AccessRoleOut:
        row = self.authz.role_display(module_key, role)
        return AccessRoleOut(key=role, name=row.name if row else role, description=row.description if row else "")

    def _role_name(self, module_key: str, role: str) -> str:
        row = self.authz.role_display(module_key, role)
        return row.name if row else role

    def _scope_from_refs(self, refs: list[str] | None) -> AccessScopeOut:
        if refs is None:
            return AccessScopeOut(all_clients=True)
        rows = self.db.execute(select(Client).where(Client.public_id.in_(refs)).order_by(Client.name)).scalars().all()
        return AccessScopeOut(all_clients=False, clients=[AccessClientOut(id=c.id, name=c.name) for c in rows])

    def _authority_out(self, module: ApplicationModule, appointment: ApplicationAdministrator) -> AccessScopeOut | None:
        if not module.supports_client_scope:
            return None
        return self._scope_from_refs(appointment.client_authority)

    def _name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        user = self.db.get(User, user_id)
        return user.full_name if user else None

    # --- authority checks ---------------------------------------------------------------

    @staticmethod
    def _role_within(ctx: _Ctx, role: str) -> bool:
        return role in ctx.definition.delegable_roles and role in (ctx.appointment.grantable_roles or [])

    @staticmethod
    def _refs_within(authority: list | None, refs: list[str] | None) -> bool:
        """``refs`` None means unrestricted (all clients)."""
        if authority is None:
            return True
        return refs is not None and set(refs) <= set(authority)

    def _direct_within(self, ctx: _Ctx, row: UserModuleRole) -> bool:
        if not self._role_within(ctx, row.role):
            return False
        if not ctx.module.supports_client_scope:
            return True
        return self._refs_within(ctx.appointment.client_authority, self.authz.client_ref_scope_for(row))

    def _group_within(self, ctx: _Ctx, group_role: GroupModuleRole) -> bool:
        if not self._role_within(ctx, group_role.role):
            return False
        if not ctx.module.supports_client_scope:
            return True
        return self._refs_within(ctx.appointment.client_authority, self.authz.group_client_ref_scope(group_role))

    def _validated_scope(self, ctx: _Ctx, role: str, client_scope: ClientScopeIn | None) -> ClientScopeIn | None:
        if not self._role_within(ctx, role):
            raise ForbiddenError(f"You are not authorised to grant the role {self._role_name(ctx.module.key, role)}.")
        if not ctx.module.supports_client_scope:
            return None
        if client_scope is None or (not client_scope.all_clients and not client_scope.client_ids):
            raise AdminError("Choose All Clients or at least one client.")
        refs = None if client_scope.all_clients else list(self.admin._resolve_client_scope_refs(client_scope).values())
        if not self._refs_within(ctx.appointment.client_authority, refs):
            raise ForbiddenError("That client scope is outside your authority.")
        return client_scope

    def _block_reason(self, ctx: _Ctx, actor: User, target: User, *, granting: bool) -> str | None:
        """Why the caller may not change this person's access here, or None."""
        if target.id == actor.id:
            return "You cannot change your own access."
        if target.platform_role in ADMIN_PLATFORM_ROLES:
            return "Platform administrators' access is managed in Central Admin."
        if protected_admin.is_protected_user(self.db, target):
            return "This account is protected; its access is managed in Central Admin."
        if self.appointment(target.id, ctx.module.key) is not None:
            return "Access administrators of this application are managed by a Super Admin."
        if self._holds_implying_role(ctx.definition, target):
            # e.g. an On-site Admin: an administrator role, assigned only by Platform / Super Admins.
            return "Administrators of this application are managed by a Platform or Super Admin."
        if granting and not target.is_active:
            return "This account is inactive."
        if granting and not self.authz.is_eligible_employee(target):
            return "Needs Central Admin verification: not yet a verified employee matched to an HR record."
        return None

    # --- reading ------------------------------------------------------------------------

    def _direct_row(self, user_id: int, module_key: str) -> UserModuleRole | None:
        return self.db.execute(
            select(UserModuleRole).where(UserModuleRole.user_id == user_id, UserModuleRole.module_key == module_key)
        ).scalars().first()

    def _group_grants(self, user: User, module_key: str) -> list[tuple[GroupModuleRole, AccessGroup]]:
        """Enabled grants for this application from the person's active groups, whether or not a
        suspension currently stops them."""
        return list(
            self.db.execute(
                select(GroupModuleRole, AccessGroup)
                .join(AccessGroup, AccessGroup.id == GroupModuleRole.access_group_id)
                .join(UserGroupMembership, UserGroupMembership.access_group_id == AccessGroup.id)
                .where(
                    UserGroupMembership.user_id == user.id,
                    AccessGroup.status == AccessGroupStatus.ACTIVE,
                    GroupModuleRole.module_key == module_key,
                    GroupModuleRole.enabled.is_(True),
                )
                .order_by(AccessGroup.display_name)
            ).all()
        )

    def _direct_source(self, module: ApplicationModule, row: UserModuleRole, suspended: bool) -> AccessSourceOut:
        return AccessSourceOut(
            type="DIRECT", role=row.role, role_name=self._role_name(module.key, row.role), applies=not suspended,
            scope=self._scope_from_refs(self.authz.client_ref_scope_for(row)) if module.supports_client_scope else None,
        )

    def _group_source(
        self, module: ApplicationModule, gr: GroupModuleRole, group: AccessGroup, suspended: bool
    ) -> AccessSourceOut:
        mandated = group.group_type == SYSTEM_GROUP_TYPE
        return AccessSourceOut(
            type="GROUP", role=gr.role, role_name=self._role_name(module.key, gr.role), group_id=group.id,
            group_name=group.display_name, mandated=mandated, applies=mandated or not suspended,
            scope=self._scope_from_refs(self.authz.group_client_ref_scope(gr)) if module.supports_client_scope else None,
        )

    def _suspension_out(self, user: User, suspension: ApplicationAccessSuspension) -> SuspensionOut:
        return SuspensionOut(
            user_id=user.id, full_name=user.full_name, email=user.email, reason=suspension.reason,
            suspended_by_name=self._name(suspension.suspended_by_user_id), suspended_at=suspension.created_at,
        )

    def _appointment_info(self, module: ApplicationModule, a: ApplicationAdministrator) -> AppointmentInfoOut:
        return AppointmentInfoOut(
            can_appoint_admins=a.can_appoint_admins,
            grantable_roles=[self._role_out(module.key, r) for r in (a.grantable_roles or [])],
            client_authority=self._authority_out(module, a),
            appointed_by_name=self._name(a.appointed_by_user_id), appointed_at=a.created_at,
        )

    def user_out(
        self, module: ApplicationModule, user: User, *, ctx: _Ctx | None = None, actor: User | None = None
    ) -> AppUserOut:
        """One person's access to one application: every source, which ones apply, and (for an
        application administrator) whether they may change it."""
        key = module.key
        suspension = self._suspension(user.id, key)
        suspended = suspension is not None
        sources: list[AccessSourceOut] = []
        direct = self._direct_row(user.id, key)
        if direct is not None and direct.enabled:
            sources.append(self._direct_source(module, direct, suspended))
        for gr, group in self._group_grants(user, key):
            sources.append(self._group_source(module, gr, group, suspended))
        baseline = self.authz.baseline_roles(user).get(key)
        if baseline:
            sources.append(AccessSourceOut(type="BASELINE", role=baseline, role_name=self._role_name(key, baseline),
                                           mandated=True))
        appointment = self.appointment(user.id, key)
        if appointment is not None:
            role = self.authz.appointment_role(appointment) or ""
            sources.append(AccessSourceOut(
                type="APPOINTMENT", role=role, role_name=self._role_name(key, role),
                applies=not suspended and self.authz.is_eligible_employee(user),
            ))

        grants = self.authz.effective_module_roles(user).get(key, []) if user.is_active else []
        primary = next((g for g in grants if g.source_type == "DIRECT"), grants[0]) if grants else None

        manageable, reason = False, None
        if ctx is not None and actor is not None:
            reason = self._block_reason(ctx, actor, user, granting=False)
            if reason is None and direct is not None and direct.enabled and not self._direct_within(ctx, direct):
                reason = "Outside your authority: managed in Central Admin."
            manageable = reason is None
        return AppUserOut(
            user_id=user.id, full_name=user.full_name, email=user.email, title=user.title, is_active=user.is_active,
            eligible_employee=self.authz.is_eligible_employee(user), has_access=primary is not None,
            role=primary.role if primary else None,
            role_name=self._role_name(key, primary.role) if primary else None,
            sources=sources, suspension=self._suspension_out(user, suspension) if suspension else None,
            administrator=self._appointment_info(module, appointment) if appointment else None,
            manageable=manageable, managed_reason=reason,
        )

    def _related_user_ids(self, module_key: str) -> set[int]:
        ids = set(self.db.execute(select(UserModuleRole.user_id).where(UserModuleRole.module_key == module_key)).scalars())
        ids |= set(
            self.db.execute(
                select(UserGroupMembership.user_id)
                .join(GroupModuleRole, GroupModuleRole.access_group_id == UserGroupMembership.access_group_id)
                .where(GroupModuleRole.module_key == module_key)
            ).scalars()
        )
        ids |= set(self.db.execute(
            select(ApplicationAdministrator.user_id).where(ApplicationAdministrator.module_key == module_key)
        ).scalars())
        ids |= set(self.db.execute(
            select(ApplicationAccessSuspension.user_id).where(ApplicationAccessSuspension.module_key == module_key)
        ).scalars())
        return ids

    def _default_note(self, module: ApplicationModule) -> str | None:
        role = self.admin._default_role(module.key)
        if role is None:
            return None
        return (f"Every eligible employee has {self._role_name(module.key, role)} access to {module.name}. "
                "It is managed centrally and cannot be removed here.")

    # --- the application's Access page (/api/access/{app}) ----------------------------

    def me(self, actor: User, module_key: str) -> AccessMeOut:
        self.require_feature()
        module, definition = self._module(module_key)
        appointment = self._active_appointment(actor, module_key)
        default_role = self.admin._default_role(module_key)
        if appointment is None:
            return AccessMeOut(module_key=module.key, module_name=module.name, is_admin=False)
        return AccessMeOut(
            module_key=module.key, module_name=module.name, is_admin=True,
            can_appoint_admins=appointment.can_appoint_admins,
            supports_client_scope=module.supports_client_scope,
            grantable_roles=[
                self._role_out(module_key, r) for r in definition.delegable_roles if r in (appointment.grantable_roles or [])
            ],
            client_authority=self._authority_out(module, appointment) if module.supports_client_scope else None,
            default_role_name=self._role_name(module_key, default_role) if default_role else None,
        )

    def list_users(self, actor: User, module_key: str) -> AppUsersOut:
        ctx = self._require_admin(actor, module_key)
        users = [self.db.get(User, uid) for uid in self._related_user_ids(module_key)]
        out = [self.user_out(ctx.module, u, ctx=ctx, actor=actor) for u in users if u is not None]
        out.sort(key=lambda u: u.full_name.lower())
        return AppUsersOut(users=out, default_access_note=self._default_note(ctx.module))

    def get_user(self, actor: User, module_key: str, user_id: int) -> AppUserOut:
        ctx = self._require_admin(actor, module_key)
        user = self.db.get(User, user_id)
        # Only people related to this application, or employees who could be given access.
        if user is None or not (user_id in self._related_user_ids(module_key) or self.authz.is_eligible_employee(user)):
            raise NotFoundError("Person not found.")
        return self.user_out(ctx.module, user, ctx=ctx, actor=actor)

    def search_people(self, actor: User, module_key: str, query: str) -> PeopleOut:
        ctx = self._require_admin(actor, module_key)
        q = (query or "").strip()
        if len(q) < 2:
            raise AdminError("Type at least 2 characters.")
        like = f"%{q.lower()}%"
        people: list[PersonOut] = []
        seen: set[int] = set()

        def add_user(user: User) -> None:
            if user.id in seen:
                return
            related = user.id in related_ids
            if not (self.authz.is_eligible_employee(user) or related):
                return
            seen.add(user.id)
            view = self.user_out(ctx.module, user, ctx=ctx, actor=actor)
            block = self._block_reason(ctx, actor, user, granting=True)
            people.append(PersonOut(
                user_id=user.id, full_name=user.full_name, email=user.email, job_title=user.title, source="DIJIONE",
                has_access=view.has_access, role_name=view.role_name,
                can_grant=block is None and view.manageable, reason=block or view.managed_reason,
            ))

        related_ids = self._related_user_ids(module_key)
        for user in self.db.execute(
            select(User).where(
                User.is_active.is_(True),
                or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)),
            ).order_by(User.full_name).limit(SEARCH_LIMIT)
        ).scalars():
            add_user(user)

        directory_available = True
        try:
            results = DirectoryService(self.db).search(q)
        except DirectoryUnavailable:
            directory_available, results = False, []
        for r in results:
            if len(people) >= SEARCH_LIMIT:
                break
            existing_id = r.get("existing_user_id")
            if existing_id:
                user = self.db.get(User, existing_id)
                if user is not None and user.is_active:
                    add_user(user)
                continue
            if r.get("employee_record") != "MATCHED":
                continue  # only employees matched to BambooHR can be added here
            people.append(PersonOut(
                entra_object_id=r["entra_object_id"], full_name=r["full_name"], email=r["email"],
                job_title=r.get("job_title"), department=r.get("department"), source="DIRECTORY", can_grant=True,
            ))
        return PeopleOut(people=people[:SEARCH_LIMIT], directory_available=directory_available)

    # --- changing access ----------------------------------------------------------------

    def _lift(self, actor: User, user: User, module_key: str, channel: str) -> bool:
        suspension = self._suspension(user.id, module_key)
        if suspension is None:
            return False
        self.audit.log(
            actor_id=actor.id, action="module_access.suspension_lifted", entity_type="ApplicationAccessSuspension",
            entity_id=suspension.id, previous_state={"user_id": user.id, "module_key": module_key,
                                                     "reason": suspension.reason},
            metadata={"channel": channel, "module_key": module_key}, subject_user_id=user.id,
        )
        self.db.delete(suspension)
        self.db.flush()
        return True

    def _grant_to(self, ctx: _Ctx, actor: User, target: User, role: str, client_scope: ClientScopeIn | None) -> AppUserOut:
        block = self._block_reason(ctx, actor, target, granting=True)
        if block:
            raise ForbiddenError(block)
        client_scope = self._validated_scope(ctx, role, client_scope)
        direct = self._direct_row(target.id, ctx.module.key)
        if direct is not None and direct.enabled and not self._direct_within(ctx, direct):
            raise ForbiddenError("This person's current access is outside your authority: it is managed in Central Admin.")
        lifted = self._lift(actor, target, ctx.module.key, APPLICATION)
        self.admin.upsert_module_assignment(
            actor=actor, target_user_id=target.id, module_key=ctx.module.key, role=role, enabled=True,
            client_scope=client_scope, channel=APPLICATION, extra_audit={"suspension_lifted": lifted} if lifted else None,
        )  # commits the lift and the assignment together
        return self.user_out(ctx.module, target, ctx=ctx, actor=actor)

    def grant(self, actor: User, module_key: str, user_id: int, role: str, client_scope: ClientScopeIn | None) -> AppUserOut:
        ctx = self._require_admin(actor, module_key)
        target = self.db.get(User, user_id)
        if target is None:
            raise NotFoundError("Person not found.")
        return self._grant_to(ctx, actor, target, role, client_scope)

    def onboard(
        self, actor: User, module_key: str, entra_object_id: str, role: str, client_scope: ClientScopeIn | None
    ) -> AppUserOut:
        """Add a directory employee (matched to BambooHR) and grant access, in one transaction."""
        ctx = self._require_admin(actor, module_key)
        self._validated_scope(ctx, role, client_scope)  # refuse before anything is created
        target = DirectoryService(self.db).onboard_for_application(
            actor=actor, object_id=entra_object_id, module_key=module_key
        )
        return self._grant_to(ctx, actor, target, role, client_scope)

    def revoke_preview(self, actor: User, module_key: str, user_id: int) -> RevokePreviewOut:
        ctx = self._require_admin(actor, module_key)
        target = self.db.get(User, user_id)
        if target is None:
            raise NotFoundError("Person not found.")
        return self._plan_removal(ctx, actor, target)[0]

    def _plan_removal(self, ctx: _Ctx, actor: User, target: User):
        module = ctx.module
        block = self._block_reason(ctx, actor, target, granting=False)
        direct = self._direct_row(target.id, module.key)
        suspended = self._suspension(target.id, module.key) is not None
        groups = self._group_grants(target, module.key)
        removable = [(gr, g) for gr, g in groups if g.group_type != SYSTEM_GROUP_TYPE]
        keeps = [self._group_source(module, gr, g, suspended) for gr, g in groups if g.group_type == SYSTEM_GROUP_TYPE]
        baseline = self.authz.baseline_roles(target).get(module.key)
        if baseline:
            keeps.append(AccessSourceOut(type="BASELINE", role=baseline, role_name=self._role_name(module.key, baseline),
                                         mandated=True))
        outside = (direct is not None and direct.enabled and not self._direct_within(ctx, direct)) or any(
            not self._group_within(ctx, gr) for gr, _g in removable
        )
        to_suspend = [] if suspended else removable
        nothing = (direct is None or not direct.enabled) and not to_suspend
        reason = block or (
            "Includes access outside your authority: ask Central Admin." if outside
            else ("Nothing here can be removed." if nothing else None)
        )
        preview = RevokePreviewOut(
            allowed=reason is None, reason=reason,
            removes_direct=self._direct_source(module, direct, False) if direct is not None and direct.enabled else None,
            suspends=[self._group_source(module, gr, g, False) for gr, g in to_suspend],
            keeps=keeps,
        )
        return preview, direct, to_suspend

    def revoke(self, actor: User, module_key: str, user_id: int, reason: str) -> AppUserOut:
        ctx = self._require_admin(actor, module_key)
        target = self.db.get(User, user_id)
        if target is None:
            raise NotFoundError("Person not found.")
        preview, direct, to_suspend = self._plan_removal(ctx, actor, target)
        if not preview.allowed:
            raise (ConflictError if preview.reason == "Nothing here can be removed." else ForbiddenError)(preview.reason)
        if direct is not None:
            self.audit.log(
                actor_id=actor.id, action="module_assignment.removed", entity_type="UserModuleRole", entity_id=direct.id,
                previous_state={"user_id": target.id, "module_key": module_key, "role": direct.role},
                metadata={"channel": APPLICATION, "module_key": module_key}, subject_user_id=target.id,
            )
            self.db.delete(direct)
        if to_suspend:
            suspension = ApplicationAccessSuspension(
                user_id=target.id, module_key=module_key, reason=reason.strip(), suspended_by_user_id=actor.id
            )
            self.db.add(suspension)
            self.db.flush()
            self.audit.log(
                actor_id=actor.id, action="module_access.suspended", entity_type="ApplicationAccessSuspension",
                entity_id=suspension.id,
                new_state={"user_id": target.id, "module_key": module_key,
                           "groups": [g.display_name for _gr, g in to_suspend], "reason": reason.strip()},
                metadata={"channel": APPLICATION, "module_key": module_key}, subject_user_id=target.id,
            )
        self.db.commit()
        return self.user_out(ctx.module, target, ctx=ctx, actor=actor)

    def lift_suspension(self, actor: User, module_key: str, user_id: int) -> AppUserOut:
        """The application administrator restores group access they (or a colleague) suspended."""
        ctx = self._require_admin(actor, module_key)
        target = self.db.get(User, user_id)
        if target is None or self._suspension(user_id, module_key) is None:
            raise NotFoundError("No suspension for this person.")
        block = self._block_reason(ctx, actor, target, granting=False)
        if block:
            raise ForbiddenError(block)
        if any(not self._group_within(ctx, gr) for gr, g in self._group_grants(target, module_key)
               if g.group_type != SYSTEM_GROUP_TYPE):
            raise ForbiddenError("The suspended access is outside your authority: ask Central Admin.")
        self._lift(actor, target, module_key, APPLICATION)
        self.db.commit()
        return self.user_out(ctx.module, target, ctx=ctx, actor=actor)

    # --- administrators -----------------------------------------------------------------

    def _administrator_out(self, module: ApplicationModule, a: ApplicationAdministrator) -> AdministratorOut:
        user = self.db.get(User, a.user_id)
        return AdministratorOut(
            user_id=a.user_id, full_name=user.full_name if user else "", email=user.email if user else "",
            can_appoint_admins=a.can_appoint_admins,
            grantable_roles=[self._role_out(module.key, r) for r in (a.grantable_roles or [])],
            client_authority=self._authority_out(module, a),
            appointed_by_name=self._name(a.appointed_by_user_id), appointed_at=a.created_at,
            eligible_employee=bool(user and self.authz.is_eligible_employee(user)),
        )

    def _administrators(self, module: ApplicationModule) -> list[AdministratorOut]:
        rows = self.db.execute(
            select(ApplicationAdministrator).where(ApplicationAdministrator.module_key == module.key)
        ).scalars().all()
        return sorted((self._administrator_out(module, a) for a in rows), key=lambda a: a.full_name.lower())

    def list_administrators(self, actor: User, module_key: str) -> list[AdministratorOut]:
        ctx = self._require_admin(actor, module_key)
        return self._administrators(ctx.module)

    def _authority(self, module: ApplicationModule, definition: DelegationDef, payload: AppointIn) -> tuple[list, list | None]:
        roles = list(dict.fromkeys(payload.grantable_roles))
        unknown = [r for r in roles if r not in definition.delegable_roles]
        if unknown:
            raise AdminError(f"Not a role that can be delegated in {module.name}: {', '.join(unknown)}")
        if not roles:
            raise AdminError("Choose at least one role the administrator may grant.")
        authority: list | None = None
        if module.supports_client_scope:
            scope = payload.client_authority
            if scope is None or (not scope.all_clients and not scope.client_ids):
                raise AdminError("Choose All Clients or at least one client for the administrator's authority.")
            authority = None if scope.all_clients else sorted(set(self.admin._resolve_client_scope_refs(scope).values()))
        return roles, authority

    def _save_appointment(
        self, *, actor: User, module: ApplicationModule, target: User, roles: list, authority: list | None,
        can_appoint: bool, channel: str, break_glass: dict | None,
    ) -> ApplicationAdministrator:
        existing = self.appointment(target.id, module.key)
        previous = None
        if existing is None:
            existing = ApplicationAdministrator(user_id=target.id, module_key=module.key)
            self.db.add(existing)
            action = "application_admin.appointed"
        else:
            previous = {"grantable_roles": existing.grantable_roles, "client_authority": existing.client_authority,
                        "can_appoint_admins": existing.can_appoint_admins}
            action = "application_admin.updated"
        existing.grantable_roles = roles
        existing.client_authority = authority
        existing.can_appoint_admins = can_appoint
        existing.appointed_by_user_id = actor.id
        self.db.flush()
        meta = {"channel": channel, "module_key": module.key}
        if break_glass:
            meta.update(break_glass)
        self.audit.log(
            actor_id=actor.id, action=action, entity_type="ApplicationAdministrator", entity_id=existing.id,
            previous_state=previous,
            new_state={"user_id": target.id, "module_key": module.key, "grantable_roles": roles,
                       "client_authority": authority if authority is not None else "ALL_CLIENTS",
                       "can_appoint_admins": can_appoint},
            metadata=meta, subject_user_id=target.id,
        )
        return existing

    def appoint_secondary(self, actor: User, module_key: str, user_id: int, payload: AppointIn) -> AdministratorOut:
        """An administrator who may appoint others adds a colleague, never beyond their own authority."""
        ctx = self._require_admin(actor, module_key)
        if not ctx.appointment.can_appoint_admins:
            raise ForbiddenError("You may not appoint other administrators.")
        if payload.can_appoint_admins:
            raise ForbiddenError("Only a Super Admin may let an administrator appoint others.")
        target = self.db.get(User, user_id)
        if target is None:
            raise NotFoundError("Person not found.")
        block = self._block_reason(ctx, actor, target, granting=True)
        if block:
            raise ForbiddenError(block)
        roles, authority = self._authority(ctx.module, ctx.definition, payload)
        if not set(roles) <= set(ctx.appointment.grantable_roles or []):
            raise ForbiddenError("You cannot give more role authority than you hold.")
        if ctx.module.supports_client_scope and not self._refs_within(ctx.appointment.client_authority, authority):
            raise ForbiddenError("You cannot give more client authority than you hold.")
        appointment = self._save_appointment(
            actor=actor, module=ctx.module, target=target, roles=roles, authority=authority, can_appoint=False,
            channel=APPLICATION, break_glass=None,
        )
        self.db.commit()
        return self._administrator_out(ctx.module, appointment)

    def remove_secondary(self, actor: User, module_key: str, user_id: int) -> None:
        ctx = self._require_admin(actor, module_key)
        if not ctx.appointment.can_appoint_admins:
            raise ForbiddenError("You may not remove administrators.")
        if user_id == actor.id:
            raise ForbiddenError("You cannot remove your own appointment.")
        appointment = self.appointment(user_id, module_key)
        if appointment is None:
            raise NotFoundError("Not an administrator of this application.")
        if appointment.can_appoint_admins:
            raise ForbiddenError("Only a Super Admin may remove an administrator who can appoint others.")
        self._delete_appointment(actor, ctx.module, appointment, APPLICATION, None)
        self.db.commit()

    def _delete_appointment(
        self, actor: User, module: ApplicationModule, appointment: ApplicationAdministrator, channel: str,
        break_glass: dict | None,
    ) -> None:
        remaining = self.db.execute(
            select(func.count(ApplicationAdministrator.id)).where(
                ApplicationAdministrator.module_key == module.key, ApplicationAdministrator.id != appointment.id
            )
        ).scalar_one()
        meta = {"channel": channel, "module_key": module.key, "last_administrator": remaining == 0}
        if break_glass:
            meta.update(break_glass)
        self.audit.log(
            actor_id=actor.id, action="application_admin.removed", entity_type="ApplicationAdministrator",
            entity_id=appointment.id,
            previous_state={"user_id": appointment.user_id, "module_key": module.key,
                            "grantable_roles": appointment.grantable_roles},
            metadata=meta, subject_user_id=appointment.user_id,
        )
        self.db.delete(appointment)

    # --- Central Admin (Super Admin) -----------------------------------------------------

    def central_administrators(self, module_key: str) -> list[AdministratorOut]:
        module, _definition = self._module(module_key, require_enabled=False)
        return self._administrators(module)

    def central_appoint(self, actor: User, module_key: str, user_id: int, payload: AppointIn) -> AdministratorOut:
        """A Super Admin appoints (or changes the authority of) an application's access administrator."""
        self.require_feature()
        module, definition = self._module(module_key)
        target = self.db.get(User, user_id)
        if target is None:
            raise NotFoundError("Person not found.")
        if not self.authz.is_eligible_employee(target):
            raise ForbiddenError("Only an active, verified employee matched to an HR record can be appointed.")
        break_glass = self.admin.guard_access_change(actor=actor, target=target, break_glass_reason=payload.break_glass_reason)
        roles, authority = self._authority(module, definition, payload)
        appointment = self._save_appointment(
            actor=actor, module=module, target=target, roles=roles, authority=authority,
            can_appoint=payload.can_appoint_admins, channel=CENTRAL, break_glass=break_glass,
        )
        if break_glass:
            self.admin.notify_break_glass(actor=actor, summary=f"Appointed self as {module.name} access administrator. "
                                          f"Reason: {break_glass['break_glass_reason']}")
        self.db.commit()
        return self._administrator_out(module, appointment)

    def central_remove_administrator(
        self, actor: User, module_key: str, user_id: int, break_glass_reason: str | None = None
    ) -> None:
        """Allowed when the feature is switched off too: removing appointments is part of a rollback."""
        module, _definition = self._module(module_key, require_enabled=False)
        appointment = self.appointment(user_id, module_key)
        if appointment is None:
            raise NotFoundError("Not an administrator of this application.")
        target = self.db.get(User, user_id)
        break_glass = self.admin.guard_access_change(actor=actor, target=target, break_glass_reason=break_glass_reason)
        self._delete_appointment(actor, module, appointment, CENTRAL, break_glass)
        self.db.commit()

    def central_suspensions(self, module_key: str) -> list[SuspensionOut]:
        module, _definition = self._module(module_key, require_enabled=False)
        rows = self.db.execute(
            select(ApplicationAccessSuspension).where(ApplicationAccessSuspension.module_key == module.key)
        ).scalars().all()
        out = []
        for s in rows:
            user = self.db.get(User, s.user_id)
            if user is not None:
                out.append(self._suspension_out(user, s))
        return sorted(out, key=lambda s: s.full_name.lower())

    def central_lift_suspension(
        self, actor: User, module_key: str, user_id: int, break_glass_reason: str | None = None
    ) -> None:
        """Central override. Allowed when the feature is switched off (rollback clean-up)."""
        self._module(module_key, require_enabled=False)
        target = self.db.get(User, user_id)
        if target is None or self._suspension(user_id, module_key) is None:
            raise NotFoundError("No suspension for this person.")
        self.admin.guard_access_change(actor=actor, target=target, break_glass_reason=break_glass_reason)
        self._lift(actor, target, module_key, CENTRAL)
        self.db.commit()
