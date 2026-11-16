"""Entra directory, employee records and photos for the Admin Center (and the signed-in person's
own photo). Everything Graph-related is read-only and server-side: the browser never sees a Graph
token, and never receives more than a bounded search result."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_internal_service, require_platform_admin, require_platform_permission
from app.db.session import get_db
from app.integrations.directory import DirectoryUnavailable, Photo
from app.models.user import User
from app.schemas.admin import (
    AddFromDirectoryIn,
    AdminUserOut,
    DirectoryUserOut,
    EmployeeRecordReconcileOut,
    EntraGroupOut,
)
from app.services.admin_service import AdminService
from app.services.directory_service import DirectoryError, DirectoryService, DuplicateUserError, photo_for

router = APIRouter(tags=["platform-directory"])
ADMIN = "/api/platform/admin"
_MANAGE = require_platform_permission("platform.admin.manage_users")


def _run(action: Callable):
    try:
        return action()
    except DuplicateUserError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc), "existing_user_id": exc.existing_user_id}
        )
    except DirectoryError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except DirectoryUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def _user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"User {user_id} not found")
    return user


def _photo_response(photo: Photo | None) -> Response:
    if photo is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND, headers={"Cache-Control": "private, max-age=900"})
    return Response(
        content=photo.content, media_type=photo.content_type, headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get(f"{ADMIN}/directory/users", response_model=list[DirectoryUserOut])
def search_directory(
    q: str = Query(min_length=2, max_length=64), _admin: User = Depends(_MANAGE), db: Session = Depends(get_db)
):
    return _run(lambda: DirectoryService(db).search(q))


@router.get(f"{ADMIN}/directory/users/{{object_id}}/photo")
def directory_photo(object_id: str, _admin: User = Depends(_MANAGE)) -> Response:
    return _run(lambda: _photo_response(photo_for(object_id)))


@router.post(f"{ADMIN}/users/from-directory", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
def add_from_directory(payload: AddFromDirectoryIn, admin: User = Depends(_MANAGE), db: Session = Depends(get_db)):
    def action():
        user = DirectoryService(db).create_from_directory(actor=admin, object_id=payload.entra_object_id)
        return AdminService(db).to_user_out(user)

    return _run(action)


@router.post(f"{ADMIN}/users/{{user_id}}/verify-directory", response_model=AdminUserOut)
def verify_directory(user_id: int, admin: User = Depends(_MANAGE), db: Session = Depends(get_db)):
    def action():
        user = DirectoryService(db).verify(actor=admin, user=_user_or_404(db, user_id))
        return AdminService(db).to_user_out(user)

    return _run(action)


@router.post(f"{ADMIN}/employee-records/reconcile", response_model=EmployeeRecordReconcileOut)
def reconcile_employee_records(admin: User = Depends(_MANAGE), db: Session = Depends(get_db)):
    return _run(lambda: DirectoryService(db).reconcile_employee_records(actor=admin))


@router.get(f"{ADMIN}/users/{{user_id}}/photo")
def user_photo(user_id: int, _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)) -> Response:
    user = _user_or_404(db, user_id)
    return _run(lambda: _photo_response(photo_for(user.entra_object_id)))


@router.get(f"{ADMIN}/users/{{user_id}}/entra-groups", response_model=list[EntraGroupOut])
def user_entra_groups(user_id: int, _admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    user = _user_or_404(db, user_id)

    def action():
        return [
            EntraGroupOut(
                object_id=g.object_id, display_name=g.display_name, group_type=g.group_type,
                membership="DIRECT" if g.direct else "INHERITED", dijione_mapping=None,
            )
            for g in DirectoryService(db).entra_groups(user)
        ]

    return _run(action)


INTERNAL = "/api/platform/internal"


@router.get(f"{INTERNAL}/directory/check", dependencies=[Depends(require_internal_service)])
def directory_check(email: str = Query(min_length=3, max_length=255)) -> dict:
    """Operational readiness check for one address (service-to-service only): can this service read
    the directory with its managed identity, and what would verification find? Read only; returns
    flags and counts, no names."""
    from app.integrations.directory import get_directory_provider, is_internal_member
    from app.integrations.people import get_employee_record_checker

    out: dict = {"directory_readable": False}
    try:
        provider = get_directory_provider()
        matches = provider.find_by_email(email)
        out.update(directory_readable=True, matches=len(matches))
        if len(matches) == 1:
            person = matches[0]
            out["internal_member"] = is_internal_member(person)
            out["employee_id_present"] = bool(person.employee_id)
            try:
                out["group_count"] = len(provider.groups(person.object_id))
                out["groups_readable"] = True
            except DirectoryUnavailable:
                out["groups_readable"] = False
            try:
                out["photo_present"] = provider.photo(person.object_id) is not None
            except DirectoryUnavailable:
                out["photo_present"] = None
            record = get_employee_record_checker().check(email=person.email, employee_id=person.employee_id)
            out["employee_record"] = record.status
            out["employee_number_present"] = bool(record.employee_number)
    except DirectoryUnavailable as exc:
        out["error"] = str(exc)
    return out


@router.post(f"{INTERNAL}/employee-records/reconcile", response_model=EmployeeRecordReconcileOut,
             dependencies=[Depends(require_internal_service)])
def reconcile_employee_records_internal(db: Session = Depends(get_db)):
    """Scheduled-style reconciliation of employee records (no human actor). Records BambooHR status
    only: never revokes, never touches assignments; LEGACY people who are not found are reported."""
    return _run(lambda: DirectoryService(db).reconcile_employee_records(actor=None))


@router.get("/api/auth/me/photo")
def my_photo(user: User = Depends(get_current_user)) -> Response:
    """The signed-in person's own photo (a staff session; a View-as token is refused upstream)."""
    try:
        return _photo_response(photo_for(user.entra_object_id))
    except DirectoryUnavailable:
        return _photo_response(None)
