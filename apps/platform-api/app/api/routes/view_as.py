"""View-as: start and end a read-only simulation of an internal employee (Admin Center)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.view_as import ViewAsEndOut, ViewAsStartIn, ViewAsStartOut, ViewAsTargetOut
from app.services.view_as_service import ViewAsError, ViewAsService

router = APIRouter(prefix="/api/platform/admin/view-as", tags=["platform-view-as"])


@router.post("", response_model=ViewAsStartOut, status_code=201)
def start_view_as(
    payload: ViewAsStartIn,
    admin: User = Depends(require_platform_permission("platform.admin.view_as")),
    db: Session = Depends(get_db),
) -> ViewAsStartOut:
    try:
        started = ViewAsService(db).start(admin, payload.target_user_id)
    except ViewAsError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    target = started.target
    return ViewAsStartOut(
        access_token=started.token,
        session_id=started.session.public_id,
        expires_at=started.session.expires_at,
        target=ViewAsTargetOut(id=target.id, full_name=target.full_name, email=target.email, title=target.title),
    )


@router.post("/{session_id}/end", response_model=ViewAsEndOut)
def end_view_as(
    session_id: str,
    admin: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ViewAsEndOut:
    try:
        ViewAsService(db).end(admin, session_id)
    except ViewAsError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return ViewAsEndOut(session_id=session_id, ended=True)
