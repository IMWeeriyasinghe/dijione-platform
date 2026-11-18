from dataclasses import dataclass

from auth_client_py.fastapi_deps import make_verify_internal_request
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    SESSION_ACTOR_CLAIM,
    SESSION_ACTOR_STAFF,
    SESSION_ACTOR_VIEW_AS,
    InvalidTokenError,
    decode_session_token,
)
from app.db.session import get_db
from app.models.user import User
from app.models.view_as_session import ViewAsSession
from app.repositories.user_repo import UserRepository
from app.services.authorization_service import AuthorizationService
from app.services.view_as_service import ViewAsInvalid, ViewAsService

_bearer_scheme = HTTPBearer(auto_error=False)


# Claims that only tokens for other actor populations carry (supplier-portal
# sessions, external client links).
_FOREIGN_ACTOR_CLAIMS = ("supplier", "external", "view_as")


def _is_staff_session(payload: dict, user: User) -> bool:
    """Positive proof that a verified token is this DijiOne user's own session.

    The signature and issuer are shared with supplier-portal tokens, so they
    prove only that a DijiOne service signed the token. A staff session must:
    carry no claim of another actor population; be marked ``actor_type=staff``
    (required: tokens from before that marker existed have all expired); and name the same email address as the
    user record its ``sub`` points at, which binds the token to that account
    rather than to whichever account happens to share the number."""
    if any(payload.get(claim) is not None for claim in _FOREIGN_ACTOR_CLAIMS):
        return False
    if payload.get(SESSION_ACTOR_CLAIM) != SESSION_ACTOR_STAFF:  # mandatory since every pre-marker token expired
        return False
    email = payload.get("email")
    return isinstance(email, str) and email.strip().lower() == user.email.strip().lower()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = decode_session_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc

    if payload.get(SESSION_ACTOR_CLAIM) == SESSION_ACTOR_VIEW_AS:
        # A read-only View-as session is never a staff session. Refuse it plainly (403, not 401, so a
        # client does not mistake it for the end of a sign-in).
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This is a read-only View-as session", headers={"X-Auth-Error": "view_as_read_only"}
        )
    user = UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    if not _is_staff_session(payload, user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return user


@dataclass(frozen=True)
class Viewer:
    """Who a read-only endpoint answers for: the signed-in user, or, in a View-as session, the
    employee being viewed (``view_as`` and ``actor_name`` are then set)."""

    user: User
    view_as: ViewAsSession | None = None
    actor_name: str | None = None


def get_viewer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> Viewer:
    """For the few GET endpoints a shell needs in order to draw itself (``/me``, the module list,
    notifications): accepts a staff session or a valid View-as session. Everything else on
    platform-api stays staff-only."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = decode_session_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    if payload.get(SESSION_ACTOR_CLAIM) == SESSION_ACTOR_VIEW_AS:
        try:
            target, session = ViewAsService(db).resolve(payload)
        except ViewAsInvalid as exc:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, str(exc), headers={"X-Auth-Error": "view_as_ended"}
            ) from exc
        return Viewer(user=target, view_as=session, actor_name=str(payload["view_as"].get("actor_name", "")))
    return Viewer(user=get_current_user(credentials, db))


def get_session_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    _user: User = Depends(get_current_user),
) -> dict:
    """The verified payload of the caller's session token (after ``get_current_user``
    has accepted it)."""
    return decode_session_token(credentials.credentials)


def require_platform_admin(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    """Any DijiOne Admin Center access (SUPER_ADMIN or PLATFORM_ADMIN)."""
    permissions = AuthorizationService(db).platform_permissions(user)
    if "platform.admin.access" not in permissions:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform admin access required")
    return user


def require_platform_permission(permission_key: str):
    """Reusable factory for platform-level (Admin Center) permission gates.
    Example: ``Depends(require_platform_permission(
    "platform.admin.manage_admins"))`` for SUPER_ADMIN-only actions."""

    def _dependency(
        user: User = Depends(get_current_user), db: Session = Depends(get_db)
    ) -> User:
        permissions = AuthorizationService(db).platform_permissions(user)
        if permission_key not in permissions:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Missing required permission: {permission_key}"
            )
        return user

    return _dependency


# Gate for service-to-service calls with no human actor behind them
# (talent-api/birthday-api writing audit events or notifications). Never used
# for anything a browser could trigger. Shared definition in
# ``packages/auth-client-py`` — the single place to swap the dev shared-secret
# for mTLS / a managed identity later (CLAUDE.md rule 21).
require_internal_service = make_verify_internal_request(
    secret=get_settings().internal_service_secret
)
