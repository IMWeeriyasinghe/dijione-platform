from auth_client_py import AuthClaims
from auth_client_py.fastapi_deps import make_get_claims, make_verify_internal_request
from fastapi import Depends, HTTPException, status

from app.core.config import get_settings
from app.core.constants import MODULE_ATWORK, PERM_MANAGEMENT_ACCESS

_settings = get_settings()

# Claims are verified locally (no call to platform-api), like every module.
get_claims = make_get_claims(secret=_settings.platform_jwt_secret, algorithm=_settings.jwt_algorithm)
require_internal_service = make_verify_internal_request(secret=_settings.internal_service_secret)


def require_atwork_permission(permission_key: str):
    """Backend gate: the permission must be in the verified DijiAtWork claim."""

    def _dependency(claims: AuthClaims = Depends(get_claims)) -> AuthClaims:
        module_claim = claims.module(MODULE_ATWORK)
        if module_claim is None or not module_claim.has(permission_key):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing required permission: {permission_key}")
        return claims

    return _dependency


def require_management_permission(permission_key: str):
    """Management routes need Management access and the specific capability.
    A role name never grants anything by itself."""

    def _dependency(claims: AuthClaims = Depends(get_claims)) -> AuthClaims:
        module_claim = claims.module(MODULE_ATWORK)
        if module_claim is None or not module_claim.has(PERM_MANAGEMENT_ACCESS):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing required permission: {PERM_MANAGEMENT_ACCESS}")
        if not module_claim.has(permission_key):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing required permission: {permission_key}")
        return claims

    return _dependency
