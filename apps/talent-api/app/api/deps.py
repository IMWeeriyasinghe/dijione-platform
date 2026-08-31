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
from auth_client_py.claims import ModuleRoleClaims
from auth_client_py.fastapi_deps import make_get_claims, make_verify_internal_request
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import MODULE_TALENT_FLOW
from app.db.session import get_db
from app.repositories.client_repo import ClientRepository

_settings = get_settings()
get_claims = make_get_claims(secret=_settings.jwt_dev_secret, algorithm=_settings.jwt_algorithm)

# Gate for service-to-service calls with no human actor behind them
# (admin-api reading client display names/counts; the recruitment
# scheduled-sync trigger). Shared definition in ``packages/auth-client-py``.
require_internal_service = make_verify_internal_request(
    secret=_settings.internal_service_secret
)


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


def _resolve_local_client_scope(
    db: Session, mc: ModuleRoleClaims
) -> tuple[int | None, list[int] | None]:
    """Map a client-scope claim to DijiTalentFlow's own integer client ids
    (Architecture Completion Plan §6.1).

    A token minted before this field existed carries only the legacy local
    integers — pass them straight through. Otherwise resolve the durable
    platform ``Client.public_id`` values to the local extension rows; a
    public id with no local ``clients`` row is silently dropped (narrower =
    fail-safe — this never widens scope). ``client_ids is None`` on the way
    out still means unrestricted (staff ALL_CLIENTS).
    """
    if mc.client_public_id is None and mc.client_public_ids is None:
        return mc.client_id, mc.client_ids

    repo = ClientRepository(db)
    client_ids: list[int] | None = None
    if mc.client_public_ids is not None:
        client_ids = sorted(c.id for c in repo.list_by_platform_ids(mc.client_public_ids))
    client_id: int | None = None
    if mc.client_public_id is not None:
        row = repo.get_by_platform_id(mc.client_public_id)
        client_id = row.id if row else None
    return client_id, client_ids


def get_talent_scope(
    claims: AuthClaims = Depends(get_claims), db: Session = Depends(get_db)
) -> TalentScope:
    module_claim = claims.module(MODULE_TALENT_FLOW)
    if module_claim is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "User has no active DijiTalentFlow module access"
        )
    client_id, client_ids = _resolve_local_client_scope(db, module_claim)
    return TalentScope(
        user=ScopeUser(id=claims.user_id, full_name=claims.full_name),
        role=module_claim.role,
        client_id=client_id,
        client_ids=client_ids,
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
