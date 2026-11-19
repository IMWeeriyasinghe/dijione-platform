"""An application's own Management → Access page: delegated access administration.

Reached through the gateway at ``/api/access/{app}/…`` with the caller's own DijiOne session. Every
endpoint takes a staff session only (``get_current_user``: a View-as token is refused, so View-as
stays read-only) and ``DelegatedAccessService`` checks the caller's appointment and authority
against the database on every request. When ``DELEGATED_ACCESS_ENABLED`` is off every endpoint
answers 404; access already granted or suspended keeps applying.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.integrations.directory import DirectoryUnavailable
from app.models.user import User
from app.schemas.app_access import (
    AccessMeOut,
    AdministratorOut,
    AppointIn,
    AppUserOut,
    AppUsersOut,
    GrantIn,
    OnboardIn,
    PeopleOut,
    RevokeIn,
    RevokePreviewOut,
)
from app.services.admin_service import AdminError, ConflictError, ForbiddenError, NotFoundError
from app.services.delegated_access_service import DelegatedAccessService
from app.services.directory_service import DirectoryError, DuplicateUserError
from app.services.protected_admin import ProtectedAdminError

router = APIRouter(prefix="/api/access/{module_key}", tags=["application-access"])


def _handle(action):
    try:
        return action()
    except ProtectedAdminError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except (ConflictError, DuplicateUserError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except (AdminError, DirectoryError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except DirectoryUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.get("/me", response_model=AccessMeOut)
def access_me(module_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _handle(lambda: DelegatedAccessService(db).me(user, module_key))


@router.get("/users", response_model=AppUsersOut)
def list_users(module_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _handle(lambda: DelegatedAccessService(db).list_users(user, module_key))


@router.get("/people", response_model=PeopleOut)
def search_people(
    module_key: str, q: str = Query(default="", max_length=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return _handle(lambda: DelegatedAccessService(db).search_people(user, module_key, q))


def _photo(photo) -> Response:
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo available")
    return Response(photo.content, media_type=photo.content_type,
                    headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


@router.get("/people/{object_id}/photo")
def directory_photo(module_key: str, object_id: str, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> Response:
    """Entra profile photo of a directory search result (application access administrators only)."""
    return _handle(lambda: _photo(DelegatedAccessService(db).directory_photo(user, module_key, object_id)))


@router.get("/users/{user_id}/photo")
def user_photo(module_key: str, user_id: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> Response:
    return _handle(lambda: _photo(DelegatedAccessService(db).user_photo(user, module_key, user_id)))


@router.get("/users/{user_id}", response_model=AppUserOut)
def get_user(module_key: str, user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _handle(lambda: DelegatedAccessService(db).get_user(user, module_key, user_id))


@router.put("/users/{user_id}", response_model=AppUserOut)
def grant(
    module_key: str, user_id: int, payload: GrantIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return _handle(lambda: DelegatedAccessService(db).grant(user, module_key, user_id, payload.role, payload.client_scope))


@router.post("/users/from-directory", response_model=AppUserOut, status_code=status.HTTP_201_CREATED)
def onboard(module_key: str, payload: OnboardIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _handle(
        lambda: DelegatedAccessService(db).onboard(
            user, module_key, payload.entra_object_id, payload.role, payload.client_scope
        )
    )


@router.get("/users/{user_id}/revoke-preview", response_model=RevokePreviewOut)
def revoke_preview(module_key: str, user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _handle(lambda: DelegatedAccessService(db).revoke_preview(user, module_key, user_id))


@router.post("/users/{user_id}/revoke", response_model=AppUserOut)
def revoke(
    module_key: str, user_id: int, payload: RevokeIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return _handle(lambda: DelegatedAccessService(db).revoke(user, module_key, user_id, payload.reason))


@router.delete("/users/{user_id}/suspension", response_model=AppUserOut)
def lift_suspension(module_key: str, user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _handle(lambda: DelegatedAccessService(db).lift_suspension(user, module_key, user_id))


@router.get("/admins", response_model=list[AdministratorOut])
def list_admins(module_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _handle(lambda: DelegatedAccessService(db).list_administrators(user, module_key))


@router.put("/admins/{user_id}", response_model=AdministratorOut)
def appoint_admin(
    module_key: str, user_id: int, payload: AppointIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return _handle(lambda: DelegatedAccessService(db).appoint_secondary(user, module_key, user_id, payload))


@router.delete("/admins/{user_id}")
def remove_admin(module_key: str, user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _handle(lambda: DelegatedAccessService(db).remove_secondary(user, module_key, user_id))
    return {"status": "removed"}
