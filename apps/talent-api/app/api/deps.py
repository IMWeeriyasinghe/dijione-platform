"""Authorization for DijiTalentFlow, resolved entirely from the JWT's signed
claims (Phase 2.5 CR §19-20) — no database join, no call back to Platform
Core on the request path. talent-api owns no ``User``/``UserModuleRole``
table; ``AuthClaims`` (from ``packages/auth-client-py``) is Platform Core's
already-authorized answer to "who is this and what can they do", computed
once at login.

``TalentScope`` keeps the exact shape the pre-split ``app/api/deps.py`` had
so every route handler in this package works unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from auth_client_py import AuthClaims
from auth_client_py.fastapi_deps import make_get_claims
from fastapi import Depends, Header, HTTPException, status

from app.core.config import get_settings
from app.core.constants import MODULE_TALENT_FLOW

_settings = get_settings()
get_claims = make_get_claims(secret=_settings.jwt_dev_secret, algorithm=_settings.jwt_algorithm)


def require_internal_service(x_internal_token: str | None = Header(default=None)) -> None:
    """Gate for service-to-service calls with no human actor behind them
    (admin-api reading client display names/counts). Dev-only shared-secret
    trust boundary — see the identical dependency in platform-api and
    docs/platform/service-contracts.md."""
    if x_internal_token != _settings.internal_service_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing internal service token")


@dataclass(frozen=True)
class ScopeUser:
    """Just enough of Platform Core's ``User`` for talent-api's needs —
    display name at write time (see Message.sender_name / Document.
    uploaded_by_name) and the id foreign services store as an opaque int."""

    id: int
    full_name: str


@dataclass
class TalentScope:
    """Resolved DijiTalentFlow authorization scope for the current user.

    ``client_id`` is not-None for TALENT_CLIENT personas — every
    tenant-scoped repository call must pass it through. It is None for
    staff roles.

    ``client_ids`` is the staff *portfolio* restriction: ``None`` means
    unrestricted (ALL_CLIENTS) cross-client access; a list means the staff
    member may only see those specific clients. It is only meaningful when
    ``client_id`` is None.

    ``permissions`` is the resolved, module-scoped permission set backing
    every authorization decision in this scope — role-name checks
    (``is_staff`` etc.) are thin convenience wrappers over it, not a
    separate source of truth.
    """

    user: ScopeUser
    role: str
    client_id: int | None
    client_ids: list[int] | None = field(default=None)
    permissions: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_staff(self) -> bool:
        return "talent.workspace.staff" in self.permissions

    def has(self, permission_key: str) -> bool:
        return permission_key in self.permissions


def get_talent_scope(claims: AuthClaims = Depends(get_claims)) -> TalentScope:
    module_claim = claims.module(MODULE_TALENT_FLOW)
    if module_claim is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "User has no active DijiTalentFlow module access"
        )
    return TalentScope(
        user=ScopeUser(id=claims.user_id, full_name=claims.full_name),
        role=module_claim.role,
        client_id=module_claim.client_id,
        client_ids=module_claim.client_ids,
        permissions=module_claim.permissions,
    )


def require_staff_scope(scope: TalentScope = Depends(get_talent_scope)) -> TalentScope:
    if not scope.is_staff:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This action requires a Talent Acquisition or Customer Success role"
        )
    return scope


def require_customer_success_scope(scope: TalentScope = Depends(get_talent_scope)) -> TalentScope:
    if not scope.has("talent.requests.review"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This action requires the talent.requests.review permission"
        )
    return scope


def require_talent_permission(permission_key: str):
    """Reusable factory for DijiTalentFlow route-level permission gates."""

    def _dependency(scope: TalentScope = Depends(get_talent_scope)) -> TalentScope:
        if not scope.has(permission_key):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Missing required permission: {permission_key}"
            )
        return scope

    return _dependency
