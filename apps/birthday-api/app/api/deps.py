from __future__ import annotations

from dataclasses import dataclass, field

from auth_client_py import AuthClaims
from auth_client_py.fastapi_deps import make_get_claims, make_verify_internal_request
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import MODULE_BIRTHDAY
from app.db.session import get_db
from app.models.supplier_user import SupplierUser

_settings = get_settings()

# Platform Core authorization integration seam (CR §9): birthday-api
# authorizes exactly the way talent-api does — decoding Platform Core's
# signed JWT claims locally, no database, no synchronous call back.
get_claims = make_get_claims(secret=_settings.jwt_dev_secret, algorithm=_settings.jwt_algorithm)

# Gate for service-to-service calls with no human actor behind them (the
# scan-trigger endpoint, invoked by an OS/cloud scheduler, not a browser
# session). Shared definition in ``packages/auth-client-py``.
require_internal_service = make_verify_internal_request(
    secret=_settings.internal_service_secret
)


@dataclass(frozen=True)
class ScopeUser:
    """Just enough of Platform Core's ``User`` for birthday-api's needs —
    the id foreign services store as an opaque int, plus display name."""

    id: int
    full_name: str


@dataclass
class BirthdayScope:
    """Resolved DijiBirthday authorization scope for the current user,
    mirroring talent-api's ``TalentScope``. ``permissions`` is the resolved,
    module-scoped permission set backing every authorization decision in
    this scope."""

    user: ScopeUser
    role: str
    permissions: frozenset[str] = field(default_factory=frozenset)

    def has(self, permission_key: str) -> bool:
        return permission_key in self.permissions


def get_birthday_scope(claims: AuthClaims = Depends(get_claims)) -> BirthdayScope:
    module_claim = claims.module(MODULE_BIRTHDAY)
    if module_claim is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User has no active DijiBirthday module access")
    return BirthdayScope(
        user=ScopeUser(id=claims.user_id, full_name=claims.full_name),
        role=module_claim.role,
        permissions=module_claim.permissions,
    )


def require_birthday_permission(permission_key: str):
    """Reusable factory for DijiBirthday route-level permission gates."""

    def _dependency(scope: BirthdayScope = Depends(get_birthday_scope)) -> BirthdayScope:
        if not scope.has(permission_key):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Missing required permission: {permission_key}"
            )
        return scope

    return _dependency


@dataclass
class SupplierScope:
    """Resolved supplier-portal authorization scope (Phase-Next §5).
    ``supplier_id`` comes exclusively from the validated token's
    ``supplier`` claim — a client can never supply/override it via a
    request parameter. Every supplier-portal repository method must take
    ``supplier_id`` from this scope, not from the URL/body, so a
    manipulated order id belonging to a different supplier 404s rather
    than ever being readable."""

    supplier_user_id: int
    supplier_id: int
    permissions: frozenset[str] = field(default_factory=frozenset)

    def has(self, permission_key: str) -> bool:
        return permission_key in self.permissions


def get_supplier_scope(
    claims: AuthClaims = Depends(get_claims), db: Session = Depends(get_db)
) -> SupplierScope:
    module_claim = claims.module(MODULE_BIRTHDAY)
    if module_claim is None or claims.supplier is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User has no active supplier-portal access")

    # Re-checked on every request, not just at token-issuance time: a
    # SupplierUser deactivated mid-token-lifetime must lose portal access
    # immediately, not only once their (up to 8h dev / longer prod) token
    # expires. supplier_id is taken from this DB row, not the claim, as a
    # second layer — the claim is still what selects *which* row, never a
    # client-supplied supplier_id.
    supplier_user = db.get(SupplierUser, claims.supplier.supplier_user_id)
    if supplier_user is None or supplier_user.status != "ACTIVE":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Supplier user is inactive or no longer exists")

    return SupplierScope(
        supplier_user_id=supplier_user.id,
        supplier_id=supplier_user.supplier_id,
        permissions=module_claim.permissions,
    )


def require_supplier_permission(permission_key: str):
    """Reusable factory for supplier-portal route-level permission gates —
    mirrors ``require_birthday_permission`` but resolves the isolated
    ``SupplierScope`` instead of the internal-staff ``BirthdayScope``."""

    def _dependency(scope: SupplierScope = Depends(get_supplier_scope)) -> SupplierScope:
        if not scope.has(permission_key):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Missing required permission: {permission_key}"
            )
        return scope

    return _dependency
