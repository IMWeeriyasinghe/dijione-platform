from __future__ import annotations

from dataclasses import dataclass, field

from auth_client_py import AuthClaims
from auth_client_py.fastapi_deps import make_get_claims, make_verify_internal_request
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import MODULE_ONSITE
from app.db.session import get_db
from app.repositories.site_repository import SiteRepository

_settings = get_settings()

# Claims are verified locally (no call to platform-api), like every module.
get_claims = make_get_claims(secret=_settings.platform_jwt_secret, algorithm=_settings.jwt_algorithm)
require_internal_service = make_verify_internal_request(secret=_settings.internal_service_secret)


@dataclass(frozen=True)
class ScopeUser:
    id: int
    full_name: str


@dataclass
class OnsiteScope:
    """Resolved Diji On-site scope. ``allowed_site_ids`` is the fail-closed
    site allow-list: V1 = every site an ONSITE_ADMIN has enabled. A future
    per-site restriction intersects this with a claim, with no change to
    any repository signature."""

    user: ScopeUser
    role: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    allowed_site_ids: tuple[str, ...] = ()

    def has(self, permission_key: str) -> bool:
        return permission_key in self.permissions

    def require_site(self, site_id: str) -> str:
        """Unknown or disabled site -> 404 (never reveals existence)."""
        if site_id not in self.allowed_site_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
        return site_id


def resolve_allowed_site_ids(db: Session) -> tuple[str, ...]:
    return tuple(SiteRepository(db).enabled_site_ids())


def get_onsite_scope(claims: AuthClaims = Depends(get_claims), db: Session = Depends(get_db)) -> OnsiteScope:
    module_claim = claims.module(MODULE_ONSITE)
    if module_claim is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User has no active Diji On-site access")
    return OnsiteScope(
        user=ScopeUser(id=claims.user_id, full_name=claims.full_name),
        role=module_claim.role,
        permissions=module_claim.permissions,
        allowed_site_ids=resolve_allowed_site_ids(db),
    )


def require_onsite_permission(permission_key: str):
    def _dependency(scope: OnsiteScope = Depends(get_onsite_scope)) -> OnsiteScope:
        if not scope.has(permission_key):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing required permission: {permission_key}")
        return scope

    return _dependency
