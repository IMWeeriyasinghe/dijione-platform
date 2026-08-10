from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.constants import MODULE_TALENT_FLOW, STAFF_ROLES, PlatformRole
from app.core.security import InvalidTokenError, get_auth_provider
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = get_auth_provider().decode_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc

    user_id = int(payload["sub"])
    user = UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_platform_admin(user: User = Depends(get_current_user)) -> User:
    if user.platform_role != PlatformRole.PLATFORM_ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform admin role required")
    return user


@dataclass
class TalentScope:
    """Resolved DijiTalentFlow authorization scope for the current user.

    ``client_id`` is not-None for TALENT_CLIENT personas — every
    tenant-scoped repository call must pass it through. It is None for
    staff roles (TA_MEMBER / CUSTOMER_SUCCESS / TA_MANAGER), meaning no
    client filter applies.
    """

    user: User
    role: str
    client_id: int | None

    @property
    def is_staff(self) -> bool:
        return self.role in {r.value for r in STAFF_ROLES}


def get_talent_scope(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> TalentScope:
    module_role = UserRepository(db).module_role_for(user.id, MODULE_TALENT_FLOW)
    if module_role is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "User has no DijiTalentFlow module role"
        )
    return TalentScope(user=user, role=module_role.role, client_id=module_role.client_id)


def require_staff_scope(scope: TalentScope = Depends(get_talent_scope)) -> TalentScope:
    if not scope.is_staff:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This action requires a Talent Acquisition or Customer Success role"
        )
    return scope


def require_customer_success_scope(scope: TalentScope = Depends(get_talent_scope)) -> TalentScope:
    if scope.role not in {"CUSTOMER_SUCCESS", "TA_MANAGER"}:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This action requires a Customer Success or TA Manager role"
        )
    return scope
