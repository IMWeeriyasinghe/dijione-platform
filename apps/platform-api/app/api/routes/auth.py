from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import get_auth_provider
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import CurrentUserOut, DevLoginRequest, DevPersonaOut, TokenResponse
from app.services.authorization_service import AuthorizationService
from app.services.claims_service import build_claims

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _require_dev_auth() -> None:
    if not get_settings().dev_auth_enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Dev Identity Mode is disabled in this environment (AUTH_MODE=entra). "
            "Use Microsoft sign-in.",
        )


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
    404s once AUTH_MODE=entra."""
    _require_dev_auth()
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
    _require_dev_auth()
    repo = UserRepository(db)
    user = repo.get_by_persona_key(payload.persona_key)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown persona")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")
    user.last_login_at = datetime.now(UTC)
    db.commit()
    # Phase 2.5: the token carries signed authorization claims so
    # talent-api/birthday-api/spark-api can authorize requests without a
    # synchronous call back to Platform Core — see claims_service.py.
    token = get_auth_provider().issue_token(user.id, **build_claims(user, db))
    return TokenResponse(access_token=token, user=_to_current_user_out(user, repo, db))


@router.get("/me", response_model=CurrentUserOut)
def get_me(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> CurrentUserOut:
    return _to_current_user_out(user, UserRepository(db), db)


@router.get("/config")
def auth_config() -> dict:
    """Public — tells the frontend which sign-in UI to render."""
    return {"auth_mode": "dev" if get_settings().dev_auth_enabled else "entra"}


@router.get("/logout")
def logout() -> dict:
    """Return the Entra front-channel logout URL (or None in dev mode). The
    frontend clears its local token and, if a URL is returned, navigates to
    it so the Entra session is also ended."""
    settings = get_settings()
    if settings.dev_auth_enabled or not settings.entra_tenant_id:
        return {"logout_url": None}
    post = settings.public_base_url or ""
    url = f"{settings.entra_authority}/oauth2/v2.0/logout"
    if post:
        url += f"?post_logout_redirect_uri={post}"
    return {"logout_url": url}
