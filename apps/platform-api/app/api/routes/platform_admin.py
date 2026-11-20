"""Platform Core's internal administration surface (Phase 2.5).

Mounted at ``/api/platform/admin/*`` — not called by browsers directly.
admin-api forwards every ``/api/admin/*`` request it receives here,
re-attaching the *original caller's* bearer token, so authorization is
always re-derived from that token by the same dependencies this route used
before the split (``require_platform_admin`` / ``require_platform_permission``)
— admin-api's word for who is calling is never trusted on its own (CR §48).

Business-rule failures raised by ``AdminService`` (not-found, last-
SUPER_ADMIN lockout, admin-role restriction) are translated to HTTP
responses here — the service layer never imports FastAPI.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin, require_platform_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.admin import (
    AccessDiagnosticsOut,
    AccessGroupCreateIn,
    AccessGroupDetailOut,
    AccessGroupOut,
    AccessGroupStatusIn,
    AccessGroupUpdateIn,
    AddGroupMemberIn,
    AdminDashboardOut,
    AdminModuleOut,
    AdminPermissionOut,
    AdminRoleOut,
    AdminUserCreateIn,
    AdminUserOut,
    ApplicationDetailOut,
    AuditLogOut,
    ClientCreateIn,
    ClientOut,
    EffectiveAccessOut,
    GroupModuleAssignmentIn,
    ModuleAssignmentIn,
    UpdatePlatformRoleIn,
    UpdateUserStatusIn,
)
from app.schemas.app_access import AdministratorOut, AppointIn, ModuleEnabledIn, SuspensionOut
from app.services.access_diagnostics import AccessDiagnosticsService
from app.services.admin_service import AdminError, AdminService, ConflictError, ForbiddenError, NotFoundError
from app.services.delegated_access_service import DelegatedAccessService
from app.services.email_admin_service import EmailAdminService, InvalidInputError
from app.services.email_dispatcher import dispatch_due
from app.services.protected_admin import ProtectedAdminError

router = APIRouter(prefix="/api/platform/admin", tags=["platform-admin"])


def _handle(action):
    try:
        return action()
    except ProtectedAdminError as exc:  # backstop: the flush guard refused a change nothing pre-checked
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except AdminError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/dashboard", response_model=AdminDashboardOut)
def get_dashboard(
    _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> AdminDashboardOut:
    return AdminService(db).dashboard()


@router.get("/clients", response_model=list[ClientOut])
def list_clients(
    _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> list[ClientOut]:
    return AdminService(db).list_clients()


@router.post("/clients", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreateIn,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> ClientOut:
    return _handle(
        lambda: AdminService(db).create_client(
            actor=admin, name=payload.name, status=payload.status
        )
    )


@router.get("/users", response_model=list[AdminUserOut])
def list_users(_admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)) -> list[AdminUserOut]:
    return AdminService(db).list_users()


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreateIn,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    return _handle(
        lambda: AdminService(db).create_user(
            actor=admin, email=payload.email, full_name=payload.full_name, title=payload.title
        )
    )


@router.get("/users/{user_id}", response_model=AdminUserOut)
def get_user(
    user_id: int, _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> AdminUserOut:
    return _handle(lambda: AdminService(db).get_user(user_id))


@router.get("/users/{user_id}/effective-access", response_model=EffectiveAccessOut)
def get_effective_access(
    user_id: int, _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> EffectiveAccessOut:
    return _handle(lambda: AdminService(db).effective_access(user_id))


@router.get("/users/{user_id}/access-diagnostics", response_model=AccessDiagnosticsOut)
def get_access_diagnostics(
    user_id: int, _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> AccessDiagnosticsOut:
    return _handle(lambda: AccessDiagnosticsService(db).diagnose(user_id))


@router.patch("/users/{user_id}/status", response_model=AdminUserOut)
def update_user_status(
    user_id: int,
    payload: UpdateUserStatusIn,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    return _handle(
        lambda: AdminService(db).set_user_active(actor=admin, target_user_id=user_id, is_active=payload.is_active)
    )


@router.patch("/users/{user_id}/platform-role", response_model=AdminUserOut)
def update_platform_role(
    user_id: int,
    payload: UpdatePlatformRoleIn,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    return _handle(
        lambda: AdminService(db).set_platform_role(
            actor=admin, target_user_id=user_id, new_role=payload.platform_role
        )
    )


@router.put("/users/{user_id}/modules/{module_key}", response_model=AdminUserOut)
def upsert_module_assignment(
    user_id: int,
    module_key: str,
    payload: ModuleAssignmentIn,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    return _handle(
        lambda: AdminService(db).upsert_module_assignment(
            actor=admin,
            target_user_id=user_id,
            module_key=module_key,
            role=payload.role,
            enabled=payload.enabled,
            client_scope=payload.client_scope,
            break_glass_reason=payload.break_glass_reason,
        )
    )


@router.delete("/users/{user_id}/modules/{module_key}", response_model=AdminUserOut)
def remove_module_assignment(
    user_id: int,
    module_key: str,
    break_glass_reason: str | None = Query(default=None, max_length=500),
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    return _handle(
        lambda: AdminService(db).remove_module_assignment(
            actor=admin, target_user_id=user_id, module_key=module_key, break_glass_reason=break_glass_reason
        )
    )


@router.post("/users/{user_id}/modules/{module_key}/restore-default", response_model=AdminUserOut)
def restore_default_access(
    user_id: int,
    module_key: str,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    return _handle(
        lambda: AdminService(db).restore_default_access(actor=admin, target_user_id=user_id, module_key=module_key)
    )


@router.get("/modules", response_model=list[AdminModuleOut])
def list_modules(
    _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> list[AdminModuleOut]:
    return AdminService(db).list_modules()


@router.get("/roles", response_model=list[AdminRoleOut])
def list_roles(_admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)) -> list[AdminRoleOut]:
    return AdminService(db).list_roles()


@router.get("/permissions", response_model=list[AdminPermissionOut])
def list_permissions(
    _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> list[AdminPermissionOut]:
    return AdminService(db).list_permissions()


@router.get("/audit", response_model=list[AuditLogOut])
def list_audit(
    entity_type: str | None = Query(default=None),
    entity_id: int | None = Query(default=None),
    user_id: int | None = Query(default=None),
    limit: int = Query(default=200, le=500),
    admin: User = Depends(require_platform_permission("platform.admin.view_audit")),
    db: Session = Depends(get_db),
) -> list[AuditLogOut]:
    return AdminService(db).list_audit(limit=limit, entity_type=entity_type, entity_id=entity_id, user_id=user_id)


# --- Access Groups (Phase 2.6, additive) ------------------------------------
# Group mutations reuse the existing "platform.admin.manage_users" permission
# (no new one-per-resource permission key — matches the catalog's current
# granularity, see app/core/permissions.py).


@router.get("/groups", response_model=list[AccessGroupOut])
def list_groups(_admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)) -> list[AccessGroupOut]:
    return AdminService(db).list_groups()


@router.post("/groups", response_model=AccessGroupDetailOut)
def create_group(
    payload: AccessGroupCreateIn,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AccessGroupDetailOut:
    return _handle(
        lambda: AdminService(db).create_group(
            actor=admin, key=payload.key, display_name=payload.display_name,
            description=payload.description, group_type=payload.group_type,
        )
    )


@router.get("/groups/{group_id}", response_model=AccessGroupDetailOut)
def get_group(
    group_id: int, _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> AccessGroupDetailOut:
    return _handle(lambda: AdminService(db).get_group(group_id))


@router.patch("/groups/{group_id}", response_model=AccessGroupDetailOut)
def update_group(
    group_id: int,
    payload: AccessGroupUpdateIn,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AccessGroupDetailOut:
    return _handle(
        lambda: AdminService(db).update_group(
            actor=admin, group_id=group_id, display_name=payload.display_name,
            description=payload.description, group_type=payload.group_type,
        )
    )


@router.patch("/groups/{group_id}/status", response_model=AccessGroupDetailOut)
def set_group_status(
    group_id: int,
    payload: AccessGroupStatusIn,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AccessGroupDetailOut:
    return _handle(lambda: AdminService(db).set_group_status(actor=admin, group_id=group_id, status=payload.status))


@router.post("/groups/{group_id}/members", response_model=AccessGroupDetailOut)
def add_group_member(
    group_id: int,
    payload: AddGroupMemberIn,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AccessGroupDetailOut:
    return _handle(
        lambda: AdminService(db).add_group_member(
            actor=admin, group_id=group_id, target_user_id=payload.user_id, break_glass_reason=payload.break_glass_reason
        )
    )


@router.delete("/groups/{group_id}/members/{user_id}", response_model=AccessGroupDetailOut)
def remove_group_member(
    group_id: int,
    user_id: int,
    break_glass_reason: str | None = Query(default=None, max_length=500),
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AccessGroupDetailOut:
    return _handle(
        lambda: AdminService(db).remove_group_member(
            actor=admin, group_id=group_id, target_user_id=user_id, break_glass_reason=break_glass_reason
        )
    )


@router.put("/groups/{group_id}/modules/{module_key}", response_model=AccessGroupDetailOut)
def upsert_group_module_assignment(
    group_id: int,
    module_key: str,
    payload: GroupModuleAssignmentIn,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AccessGroupDetailOut:
    return _handle(
        lambda: AdminService(db).upsert_group_module_assignment(
            actor=admin, group_id=group_id, module_key=module_key, role=payload.role,
            enabled=payload.enabled, client_scope=payload.client_scope,
            break_glass_reason=payload.break_glass_reason,
        )
    )


@router.delete("/groups/{group_id}/modules/{module_key}", response_model=AccessGroupDetailOut)
def remove_group_module_assignment(
    group_id: int,
    module_key: str,
    break_glass_reason: str | None = Query(default=None, max_length=500),
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AccessGroupDetailOut:
    return _handle(
        lambda: AdminService(db).remove_group_module_assignment(
            actor=admin, group_id=group_id, module_key=module_key, break_glass_reason=break_glass_reason
        )
    )


@router.get("/applications/{module_key}", response_model=ApplicationDetailOut)
def application_detail(
    module_key: str, _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> ApplicationDetailOut:
    return _handle(lambda: AdminService(db).application_detail(module_key))


# --- Delegated application access: appointments, suspensions, registry switch -------------------


@router.get("/applications/{module_key}/administrators", response_model=list[AdministratorOut])
def list_application_administrators(
    module_key: str, _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> list[AdministratorOut]:
    return _handle(lambda: DelegatedAccessService(db).central_administrators(module_key))


@router.put("/applications/{module_key}/administrators/{user_id}", response_model=AdministratorOut)
def appoint_application_administrator(
    module_key: str,
    user_id: int,
    payload: AppointIn,
    admin: User = Depends(require_platform_permission("platform.admin.manage_admins")),
    db: Session = Depends(get_db),
) -> AdministratorOut:
    return _handle(lambda: DelegatedAccessService(db).central_appoint(admin, module_key, user_id, payload))


@router.delete("/applications/{module_key}/administrators/{user_id}")
def remove_application_administrator(
    module_key: str,
    user_id: int,
    break_glass_reason: str | None = Query(default=None, max_length=500),
    admin: User = Depends(require_platform_permission("platform.admin.manage_admins")),
    db: Session = Depends(get_db),
) -> dict:
    _handle(lambda: DelegatedAccessService(db).central_remove_administrator(admin, module_key, user_id, break_glass_reason))
    return {"status": "removed"}


@router.get("/applications/{module_key}/suspensions", response_model=list[SuspensionOut])
def list_application_suspensions(
    module_key: str, _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> list[SuspensionOut]:
    return _handle(lambda: DelegatedAccessService(db).central_suspensions(module_key))


@router.delete("/applications/{module_key}/suspensions/{user_id}")
def lift_application_suspension(
    module_key: str,
    user_id: int,
    break_glass_reason: str | None = Query(default=None, max_length=500),
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> dict:
    _handle(lambda: DelegatedAccessService(db).central_lift_suspension(admin, module_key, user_id, break_glass_reason))
    return {"status": "lifted"}


@router.patch("/modules/{module_key}", response_model=AdminModuleOut)
def set_module_enabled(
    module_key: str,
    payload: ModuleEnabledIn,
    admin: User = Depends(require_platform_permission("platform.admin.manage_modules")),
    db: Session = Depends(get_db),
) -> AdminModuleOut:
    """Enable or disable an application. Disabling ends every session that carried it (each
    person's access version is raised, so applications refuse the old token and the browser
    refreshes to a token without the application)."""
    return _handle(lambda: AdminService(db).set_module_enabled(actor=admin, module_key=module_key, enabled=payload.enabled))


# --- Notifications (email outbox) -------------------------------------------------------------
# Reads need the audit permission (history shows recipients); every change needs Manage Modules
# (platform configuration). View-as sessions never reach these: get_current_user refuses them.


_VIEW_NOTIFICATIONS = "platform.admin.view_audit"
_MANAGE_NOTIFICATIONS = "platform.admin.manage_modules"


class NotificationEventIn(BaseModel):
    enabled: bool


class EmailTestRecipientIn(BaseModel):
    address: str = Field(min_length=3, max_length=255)
    label: str = Field(default="", max_length=255)


def _handle_email(action):
    try:
        return _handle(action)
    except InvalidInputError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/notifications/summary")
def notifications_summary(
    _admin: User = Depends(require_platform_permission(_VIEW_NOTIFICATIONS)), db: Session = Depends(get_db)
) -> dict:
    return EmailAdminService(db).summary()


@router.get("/notifications/outbox")
def notifications_outbox(
    application: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    recipient: str | None = Query(default=None, max_length=255),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_platform_permission(_VIEW_NOTIFICATIONS)),
    db: Session = Depends(get_db),
) -> dict:
    return EmailAdminService(db).list_outbox(application=application, event_type=event_type, recipient=recipient,
                                             status=status_filter, limit=limit, offset=offset)


@router.get("/notifications/outbox/{outbox_id}")
def notification_detail(
    outbox_id: int,
    _admin: User = Depends(require_platform_permission(_VIEW_NOTIFICATIONS)),
    db: Session = Depends(get_db),
) -> dict:
    return _handle_email(lambda: EmailAdminService(db).get(outbox_id))


@router.post("/notifications/outbox/{outbox_id}/retry")
def notification_retry(
    outbox_id: int,
    admin: User = Depends(require_platform_permission(_MANAGE_NOTIFICATIONS)),
    db: Session = Depends(get_db),
) -> dict:
    return _handle_email(lambda: EmailAdminService(db).retry(actor=admin, outbox_id=outbox_id))


@router.post("/notifications/dispatch")
def notifications_dispatch(
    _admin: User = Depends(require_platform_permission(_MANAGE_NOTIFICATIONS)),
) -> dict:
    """Process due notifications now (the background dispatcher does this every interval)."""
    return {"processed": dispatch_due()}


@router.get("/notifications/events")
def notification_events(
    _admin: User = Depends(require_platform_permission(_VIEW_NOTIFICATIONS)), db: Session = Depends(get_db)
) -> list[dict]:
    return EmailAdminService(db).list_events()


@router.put("/notifications/events/{event_type}")
def set_notification_event(
    event_type: str,
    payload: NotificationEventIn,
    admin: User = Depends(require_platform_permission(_MANAGE_NOTIFICATIONS)),
    db: Session = Depends(get_db),
) -> list[dict]:
    return _handle_email(lambda: EmailAdminService(db).set_event(actor=admin, event_type=event_type,
                                                                 enabled=payload.enabled))


@router.get("/notifications/test-recipients")
def list_test_recipients(
    _admin: User = Depends(require_platform_permission(_VIEW_NOTIFICATIONS)), db: Session = Depends(get_db)
) -> list[dict]:
    return EmailAdminService(db).list_recipients()


@router.post("/notifications/test-recipients", status_code=status.HTTP_201_CREATED)
def add_test_recipient(
    payload: EmailTestRecipientIn,
    admin: User = Depends(require_platform_permission(_MANAGE_NOTIFICATIONS)),
    db: Session = Depends(get_db),
) -> list[dict]:
    return _handle_email(lambda: EmailAdminService(db).add_recipient(actor=admin, address=payload.address,
                                                                     label=payload.label))


@router.delete("/notifications/test-recipients/{recipient_id}")
def remove_test_recipient(
    recipient_id: int,
    admin: User = Depends(require_platform_permission(_MANAGE_NOTIFICATIONS)),
    db: Session = Depends(get_db),
) -> list[dict]:
    return _handle_email(lambda: EmailAdminService(db).remove_recipient(actor=admin, recipient_id=recipient_id))
