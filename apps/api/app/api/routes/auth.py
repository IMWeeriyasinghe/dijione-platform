from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import get_auth_provider
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import CurrentUserOut, DevLoginRequest, DevPersonaOut, TokenResponse
from app.services.authorization_service import AuthorizationService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _module_roles_payload(user: User, repo: UserRepository) -> list[dict]:
    return [
        {"module_key": r.module_key, "role": r.role, "client_id": r.client_id, "enabled": r.enabled}
        for r in repo.module_roles_for(user.id)
    ]


def _to_current_user_out(user: User, repo: UserRepository, db: Session) -> CurrentUserOut:
    return CurrentUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        title=user.title,
        platform_role=user.platform_role,
        avatar_color=user.avatar_color,
        module_roles=_module_roles_payload(user, repo),
        platform_permissions=sorted(AuthorizationService(db).platform_permissions(user)),
    )


@router.get("/dev-personas", response_model=list[DevPersonaOut])
def list_dev_personas(db: Session = Depends(get_db)) -> list[DevPersonaOut]:
    """Public listing used by the local DEV IDENTITY MODE persona switcher.
    Not present/enabled once DEV_IDENTITY_MODE is off (CLAUDE.md §13)."""
    repo = UserRepository(db)
    return [
        DevPersonaOut(
            persona_key=u.persona_key,
            full_name=u.full_name,
            title=u.title,
            platform_role=u.platform_role,
            module_roles=_module_roles_payload(u, repo),
            avatar_color=u.avatar_color,
        )
        for u in repo.list_active_personas()
    ]


@router.post("/dev-login", response_model=TokenResponse)
def dev_login(payload: DevLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    repo = UserRepository(db)
    user = repo.get_by_persona_key(payload.persona_key)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown persona")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")
    user.last_login_at = datetime.now(UTC)
    db.commit()
    token = get_auth_provider().issue_token(user.id)
    return TokenResponse(access_token=token, user=_to_current_user_out(user, repo, db))


@router.get("/me", response_model=CurrentUserOut)
def get_me(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> CurrentUserOut:
    return _to_current_user_out(user, UserRepository(db), db)
