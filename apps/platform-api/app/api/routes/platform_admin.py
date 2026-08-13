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
    AdminDashboardOut,
    AdminModuleOut,
    AdminPermissionOut,
    AdminRoleOut,
    AdminUserOut,
    AuditLogOut,
    EffectiveAccessOut,
    ModuleAssignmentIn,
    UpdatePlatformRoleIn,
    UpdateUserStatusIn,
)
from app.services.admin_service import AdminError, AdminService, ForbiddenError, NotFoundError

router = APIRouter(prefix="/api/platform/admin", tags=["platform-admin"])


def _handle(action):
    try:
        return action()
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
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
