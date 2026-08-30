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
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin, require_platform_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.admin import (
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
    AdminUserOut,
    ApplicationDetailOut,
    AuditLogOut,
    EffectiveAccessOut,
    GroupModuleAssignmentIn,
    ModuleAssignmentIn,
    UpdatePlatformRoleIn,
    UpdateUserStatusIn,
)
from app.services.admin_service import AdminError, AdminService, ForbiddenError, NotFoundError
from app.services.client_directory import ClientDirectoryUnavailableError

router = APIRouter(prefix="/api/platform/admin", tags=["platform-admin"])


def _handle(action):
    try:
        return action()
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ClientDirectoryUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Cannot validate client scope: DijiTalentFlow (client directory) is unavailable. "
            "Try again once it is reachable.",
        ) from exc
    except AdminError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/dashboard", response_model=AdminDashboardOut)
def get_dashboard(
    _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> AdminDashboardOut:
    return AdminService(db).dashboard()


@router.get("/users", response_model=list[AdminUserOut])
def list_users(_admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)) -> list[AdminUserOut]:
    return AdminService(db).list_users()


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
        )
    )


@router.delete("/users/{user_id}/modules/{module_key}", response_model=AdminUserOut)
def remove_module_assignment(
    user_id: int,
    module_key: str,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    return _handle(
        lambda: AdminService(db).remove_module_assignment(actor=admin, target_user_id=user_id, module_key=module_key)
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
    limit: int = Query(default=200, le=500),
    admin: User = Depends(require_platform_permission("platform.admin.view_audit")),
    db: Session = Depends(get_db),
) -> list[AuditLogOut]:
    return AdminService(db).list_audit(limit=limit, entity_type=entity_type)


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
        lambda: AdminService(db).add_group_member(actor=admin, group_id=group_id, target_user_id=payload.user_id)
    )


@router.delete("/groups/{group_id}/members/{user_id}", response_model=AccessGroupDetailOut)
def remove_group_member(
    group_id: int,
    user_id: int,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AccessGroupDetailOut:
    return _handle(
        lambda: AdminService(db).remove_group_member(actor=admin, group_id=group_id, target_user_id=user_id)
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
        )
    )


@router.delete("/groups/{group_id}/modules/{module_key}", response_model=AccessGroupDetailOut)
def remove_group_module_assignment(
    group_id: int,
    module_key: str,
    admin: User = Depends(require_platform_permission("platform.admin.manage_users")),
    db: Session = Depends(get_db),
) -> AccessGroupDetailOut:
    return _handle(
        lambda: AdminService(db).remove_group_module_assignment(actor=admin, group_id=group_id, module_key=module_key)
    )


@router.get("/applications/{module_key}", response_model=ApplicationDetailOut)
def application_detail(
    module_key: str, _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> ApplicationDetailOut:
    return _handle(lambda: AdminService(db).application_detail(module_key))
