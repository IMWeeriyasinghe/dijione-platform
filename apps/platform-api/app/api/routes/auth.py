from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Viewer, get_current_user, get_session_payload, get_viewer
from app.core.config import get_settings
from app.core.security import issue_session_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import CurrentUserOut, DevLoginRequest, DevPersonaOut, TokenResponse
from app.schemas.view_as import ViewAsInfoOut
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


def issue_user_session(user: User, db: Session, *, session_started_at: datetime | None = None) -> str:
    """Mint the session token with freshly resolved claims. ``sst`` records when the
    user authenticated; a refreshed token keeps it and never outlives
    ``session_max_minutes`` from that moment."""
    settings = get_settings()
    now = datetime.now(UTC)
    started = session_started_at or now
    session_end = started + timedelta(minutes=settings.session_max_minutes)
    expires = min(now + timedelta(minutes=settings.jwt_expires_minutes), session_end)
    # The version is read BEFORE the claims are built. A change that commits in between
    # leaves the token one version behind, so it is revoked and refreshed; the other
    # order could stamp an old claim set with a new version and miss the change.
    access_version = db.execute(
        select(User.access_version).where(User.id == user.id).execution_options(populate_existing=True)
    ).scalar_one()
    claims = build_claims(user, db)
    return issue_session_token(user.id, **claims, av=access_version, sst=int(started.timestamp()), exp=expires)


def _effective_module_roles_payload(user: User, db: Session) -> list[dict]:
    """The roles the session token carries: direct, Access Group and default
    grants, enabled only. Frontends gate their shells on this list, so it must
    never disagree with what the APIs enforce from the token."""
    return [
        {"module_key": module_key, "role": claim["role"], "client_id": claim["client_id"], "enabled": True}
        for module_key, claim in build_claims(user, db)["module_roles"].items()
    ]


def _to_current_user_out(user: User, repo: UserRepository, db: Session) -> CurrentUserOut:
    return CurrentUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        title=user.title,
        platform_role=user.platform_role,
        avatar_color=user.avatar_color,
        module_roles=_effective_module_roles_payload(user, db),
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
    token = issue_user_session(user, db)
    return TokenResponse(access_token=token, user=_to_current_user_out(user, repo, db))


@router.post("/refresh", response_model=TokenResponse)
def refresh_session(
    user: User = Depends(get_current_user),
    payload: dict = Depends(get_session_payload),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Re-issue the caller's session token with their current access, so a grant or
    revocation made in the Admin Center applies without signing in again. Works only
    from a still-valid token of an active user and never extends the sign-in beyond
    ``session_max_minutes``. It is not a sign-in: ``last_login_at`` is untouched."""
    started = datetime.fromtimestamp(int(payload.get("sst") or payload["iat"]), UTC)
    if datetime.now(UTC) >= started + timedelta(minutes=get_settings().session_max_minutes):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has expired. Please sign in again.")
    token = issue_user_session(user, db, session_started_at=started)
    return TokenResponse(access_token=token, user=_to_current_user_out(user, UserRepository(db), db))


@router.get("/me", response_model=CurrentUserOut)
def get_me(viewer: Viewer = Depends(get_viewer), db: Session = Depends(get_db)) -> CurrentUserOut:
    out = _to_current_user_out(viewer.user, UserRepository(db), db)
    if viewer.view_as is not None:
        out.view_as = ViewAsInfoOut(
            session_id=viewer.view_as.public_id, expires_at=viewer.view_as.expires_at,
            actor_id=viewer.view_as.admin_user_id, actor_name=viewer.actor_name or "",
        )
    return out


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
