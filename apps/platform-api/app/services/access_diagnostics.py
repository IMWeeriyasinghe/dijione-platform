"""Effective Access Diagnostics: a read-only explanation of why a person has,
or lacks, access. Everything shown is derived from the same resolution code that
builds the session token (``AuthorizationService``); nothing here writes, and
nothing is inferred that is not recorded."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.access_group import AccessGroup, GroupModuleRole, UserGroupMembership
from app.models.audit_log import AuditLog
from app.models.module import ApplicationModule
from app.models.module_baseline import ModuleBaselineRole
from app.models.user import User, UserModuleRole
from app.schemas.admin import (
    AccessDiagnosticsOut,
    ClientScopeOut,
    DiagAccountOut,
    DiagCheckOut,
    DiagDefaultAccessOut,
    DiagGroupGrantOut,
    DiagGroupOut,
    DiagInactiveOut,
    DiagModuleOut,
    DiagSessionOut,
    DiagSourceOut,
)
from app.services.admin_service import AdminService, NotFoundError
from app.services.authorization_service import AuthorizationService

_TOKEN_NOTE = (
    "Not recorded. Session tokens are verified locally by each application and the "
    "platform keeps no log of when a token was issued or refreshed, so token freshness "
    "cannot be shown. Only the last sign-in time is recorded."
)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class AccessDiagnosticsService:
    def __init__(self, db: Session):
        self.db = db
        self.authz = AuthorizationService(db)
        self.admin = AdminService(db)

    # --- helpers ------------------------------------------------------------

    def _scope_text(self, scope: list[int] | None, uses_scope: bool) -> str:
        if not uses_scope:
            return "Not client-scoped"
        if scope is None:
            return "All clients"
        if not scope:
            return "No clients"
        names = self.admin._client_scope_out(scope).client_names
        return ", ".join(names)

    def _default_access(self, user: User, modules: dict[str, ApplicationModule]) -> list[DiagDefaultAccessOut]:
        granted = self.authz.baseline_roles(user)
        excluded = set(self.authz.baseline_exclusions(user))
        rows = self.db.execute(
            select(ModuleBaselineRole.module_key, ModuleBaselineRole.role).where(ModuleBaselineRole.enabled.is_(True))
        ).all()
        out: list[DiagDefaultAccessOut] = []
        for module_key, role in sorted(rows):
            module = modules.get(module_key)
            name = module.name if module else module_key
            reasons: list[str] = []
            if (module_key, role) in excluded:
                state = "EXCLUDED"
                reasons.append("Default access was removed for this person; it can be restored.")
            elif module is not None and not module.enabled:
                state = "MODULE_DISABLED"
                reasons.append("The application is disabled.")
            elif module_key in granted:
                state = "GRANTED"
                reasons.append("Included for every eligible employee (verified identity and employee record); always on.")
                if user.employee_record_status == "LEGACY":
                    reasons.append("Eligible from before employee-record checks; HR reconciliation is still to be confirmed.")
            else:
                state = "NOT_ELIGIBLE"
                if not user.is_active:
                    reasons.append("The account is inactive.")
                if user.identity_provider != "ENTRA" or not user.entra_object_id or not user.internal_employee:
                    reasons.append(
                        "The identity is not verified yet: verify it with the directory, or it is verified at the "
                        "person's first Microsoft sign-in."
                    )
                if user.employee_record_status not in ("MATCHED", "LEGACY"):
                    reasons.append(
                        "Not matched to a BambooHR employee record"
                        + (" (the HR system could not be reached)." if user.employee_record_status == "UNKNOWN" else ".")
                    )
            out.append(
                DiagDefaultAccessOut(module_key=module_key, module_name=name, role=role, state=state, reasons=reasons)
            )
        return out

    def _groups(self, user: User) -> list[DiagGroupOut]:
        stmt = (
            select(AccessGroup)
            .join(UserGroupMembership, UserGroupMembership.access_group_id == AccessGroup.id)
            .where(UserGroupMembership.user_id == user.id)
            .order_by(AccessGroup.display_name)
        )
        out = []
        for group in self.db.execute(stmt).scalars().all():
            grants = self.db.execute(
                select(GroupModuleRole).where(GroupModuleRole.access_group_id == group.id)
            ).scalars().all()
            out.append(
                DiagGroupOut(
                    group_id=group.id,
                    group_name=group.display_name,
                    status=str(getattr(group.status, "value", group.status)),
                    grants=[
                        DiagGroupGrantOut(module_key=g.module_key, role=g.role, enabled=bool(g.enabled))
                        for g in sorted(grants, key=lambda g: g.module_key)
                    ],
                )
            )
        return out

    def _session(self, user: User) -> DiagSessionOut:
        last = _aware(user.last_login_at)
        changes: int | None = None
        latest: datetime | None = None
        if last is not None:
            rows = self.db.execute(
                select(AuditLog.created_at).where(
                    AuditLog.subject_user_id == user.id, AuditLog.action != "user.created"
                )
            ).scalars().all()
            later = [t for t in (_aware(r) for r in rows) if t is not None and t > last]
            changes = len(later)
            latest = max(later) if later else None
        return DiagSessionOut(
            last_sign_in_at=last,
            token_issue_time_note=_TOKEN_NOTE,
            access_changes_since_last_sign_in=changes,
            latest_access_change_at=latest,
            token_lifetime_minutes=get_settings().jwt_expires_minutes,
        )

    # --- main ---------------------------------------------------------------

    def diagnose(self, user_id: int) -> AccessDiagnosticsOut:
        user = self.db.get(User, user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")

        modules = {m.key: m for m in self.db.execute(select(ApplicationModule)).scalars().all()}
        effective = {m.module_key: m for m in self.admin.effective_access(user_id).modules}
        groups = self._groups(user)
        inactive_groups = {g.group_name for g in groups if g.status != "ACTIVE"}

        direct = self.db.execute(select(UserModuleRole).where(UserModuleRole.user_id == user.id)).scalars().all()
        baseline = self.authz.baseline_roles(user)

        exclusions = {k for k, _role in self.authz.baseline_exclusions(user)}
        keys = (
            set(effective)
            | {mr.module_key for mr in direct}
            | {g.module_key for grp in groups for g in grp.grants}
            | exclusions
        )

        module_out: list[DiagModuleOut] = []
        for module_key in sorted(keys):
            eff = effective.get(module_key)
            module = modules.get(module_key)
            uses_scope = bool(module.supports_client_scope) if module else True
            sources: list[DiagSourceOut] = []
            for mr in direct:
                if mr.module_key == module_key and mr.enabled:
                    sources.append(
                        DiagSourceOut(
                            type="DIRECT",
                            role=mr.role,
                            permissions=sorted(self.authz._permissions_for(module_key, mr.role)),
                            client_scope=self._scope_text(self.authz.client_scope_for(mr), uses_scope),
                        )
                    )
            member_group_ids = [
                g.id for g in self.authz.groups_for_user(user.id)
            ]
            if member_group_ids:
                group_rows = self.db.execute(
                    select(GroupModuleRole, AccessGroup)
                    .join(AccessGroup, AccessGroup.id == GroupModuleRole.access_group_id)
                    .where(
                        GroupModuleRole.access_group_id.in_(member_group_ids),
                        GroupModuleRole.module_key == module_key,
                        GroupModuleRole.enabled.is_(True),
                    )
                ).all()
                for gr, group in group_rows:
                    sources.append(
                        DiagSourceOut(
                            type="GROUP",
                            role=gr.role,
                            group_name=group.display_name,
                            permissions=sorted(self.authz._permissions_for(module_key, gr.role)),
                            client_scope=self._scope_text(self.admin._group_client_scope(gr), uses_scope),
                        )
                    )
            if module_key in baseline:
                sources.append(
                    DiagSourceOut(
                        type="DEFAULT",
                        role=baseline[module_key],
                        permissions=sorted(self.authz._permissions_for(module_key, baseline[module_key])),
                        client_scope="Not client-scoped",
                    )
                )

            inactive: list[DiagInactiveOut] = []
            for mr in direct:
                if mr.module_key == module_key and not mr.enabled:
                    inactive.append(
                        DiagInactiveOut(type="DIRECT", role=mr.role, reason="Assignment is disabled; it grants nothing.")
                    )
            for group in groups:
                for grant in group.grants:
                    if grant.module_key != module_key:
                        continue
                    if group.group_name in inactive_groups:
                        inactive.append(
                            DiagInactiveOut(
                                type="GROUP", role=grant.role, group_name=group.group_name,
                                reason="The group is inactive, so its grants do not apply.",
                            )
                        )
                    elif not grant.enabled:
                        inactive.append(
                            DiagInactiveOut(
                                type="GROUP", role=grant.role, group_name=group.group_name,
                                reason="The group's grant for this application is disabled.",
                            )
                        )

            if module_key in exclusions:
                inactive.append(
                    DiagInactiveOut(
                        type="DEFAULT",
                        role=next(r for k, r in self.authz.baseline_exclusions(user) if k == module_key),
                        reason="Default access was removed for this person; it can be restored.",
                    )
                )

            if eff is None or not user.is_active:
                explanation = "No access to this application: nothing recorded here currently applies."
            elif not uses_scope:
                explanation = "This application does not use client scope."
            elif eff.client_scope.all_clients:
                explanation = (
                    "Unrestricted: at least one source gives access to all clients, or has no client limit recorded."
                )
            else:
                explanation = "Restricted to the union of the clients granted by every source above."
            module_out.append(
                DiagModuleOut(
                    module_key=module_key,
                    module_name=modules[module_key].name if module_key in modules else module_key,
                    has_access=eff is not None and user.is_active,
                    role=eff.role if eff else "",
                    role_name=eff.role_name if eff else "",
                    permissions=eff.permissions if eff else [],
                    sources=sources,
                    client_scope=eff.client_scope if eff else ClientScopeOut(all_clients=False),
                    uses_client_scope=uses_scope,
                    scope_explanation=explanation,
                    inactive=inactive,
                )
            )

        session = self._session(user)
        account = DiagAccountOut(
            is_active=user.is_active,
            identity_provider=user.identity_provider,
            entra_linked=bool(user.entra_object_id),
            internal_employee=bool(user.internal_employee),
            platform_role=user.platform_role,
            platform_permissions=sorted(self.authz.platform_permissions(user)),
            last_sign_in_at=_aware(user.last_login_at),
            created_at=_aware(user.created_at),
        )
        default_access = self._default_access(user, modules)
        return AccessDiagnosticsOut(
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            account=account,
            default_access=default_access,
            groups=groups,
            modules=module_out,
            session=session,
            checks=self._checks(account, default_access, module_out, session),
        )

    def _checks(
        self,
        account: DiagAccountOut,
        default_access: list[DiagDefaultAccessOut],
        modules: list[DiagModuleOut],
        session: DiagSessionOut,
    ) -> list[DiagCheckOut]:
        checks: list[DiagCheckOut] = []

        def add(key: str, level: str, message: str) -> None:
            checks.append(DiagCheckOut(key=key, level=level, message=message))

        if not account.is_active:
            add("account_inactive", "warning", "The account is inactive, so the person cannot sign in and holds no access.")
        else:
            add("account_active", "ok", "The account is active.")
        if account.last_sign_in_at is None:
            add("never_signed_in", "info", "This person has never signed in, so no session carries these roles yet.")
        if not account.entra_linked:
            add(
                "not_linked",
                "info",
                "Identity not verified yet. Use Verify with directory, or the link is made at first sign-in by matching "
                "the email address.",
            )
        elif not account.internal_employee:
            add(
                "not_internal",
                "info",
                "Linked to Microsoft but not verified as an internal employee, so default access does not apply.",
            )
        for d in default_access:
            if d.state == "EXCLUDED":
                add(f"default_excluded_{d.module_key}", "info", f"Default access to {d.module_name} was removed for this person.")
        if not any(m.has_access for m in modules):
            if account.is_active:
                add("no_access", "warning", "The person has no application access from any source.")
        for m in modules:
            if m.has_access and m.uses_client_scope and m.client_scope.all_clients and m.sources:
                add(
                    f"unrestricted_{m.module_key}",
                    "info",
                    f"{m.module_name}: access is not limited to specific clients.",
                )
            for i in m.inactive:
                add(
                    f"inactive_{m.module_key}",
                    "info",
                    f"{m.module_name}: a {i.type.lower()} {i.role} grant does nothing ({i.reason}).",
                )
        if session.access_changes_since_last_sign_in:
            add(
                "changes_since_sign_in",
                "info",
                f"{session.access_changes_since_last_sign_in} change(s) were recorded after the last sign-in. A session "
                "started before a change keeps its earlier roles until it refreshes or expires "
                f"(up to {session.token_lifetime_minutes // 60} hours).",
            )
        add("token_freshness", "info", "Token freshness is unavailable: the platform does not record token issue times.")
        return checks

