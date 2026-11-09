import time

from auth_client_py import AuthClaims, PlatformClient
from auth_client_py.fastapi_deps import make_get_claims, make_verify_internal_request
from fastapi import Depends, HTTPException, status

from app.core.config import get_settings
from app.core.constants import MODULE_ATWORK, PERM_MANAGEMENT_ACCESS, SERVICE_NAME

_settings = get_settings()
_LIVE_TTL_SECONDS = 30
_live_cache: dict[int, tuple[float, frozenset[str]]] = {}

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


def _live_check_enabled() -> bool:
    return _settings.app_env != "test"


def _fetch_live_permissions(user_id: int) -> frozenset[str] | None:
    """Platform Core's current answer; None means it could not be confirmed."""
    client = PlatformClient(_settings.platform_api_url, _settings.internal_service_secret, timeout=20.0, caller=SERVICE_NAME)
    try:
        body = client.get_internal(f"/api/platform/internal/users/{user_id}/modules/{MODULE_ATWORK}/permissions").json()
    except Exception:  # noqa: BLE001 - any failure is "not confirmed"
        return None
    return frozenset(body["permissions"]) if body.get("active") else frozenset()


def _live_permissions(user_id: int) -> frozenset[str] | None:
    cached = _live_cache.get(user_id)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    permissions = _fetch_live_permissions(user_id)
    if permissions is not None:
        _live_cache[user_id] = (time.monotonic() + _LIVE_TTL_SECONDS, permissions)
    return permissions


def require_management_permission(permission_key: str):
    """Management routes need Management access and the specific capability.
    A role name never grants anything by itself."""

    def _dependency(claims: AuthClaims = Depends(get_claims)) -> AuthClaims:
        module_claim = claims.module(MODULE_ATWORK)
        if module_claim is None or not module_claim.has(PERM_MANAGEMENT_ACCESS):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing required permission: {PERM_MANAGEMENT_ACCESS}")
        if not module_claim.has(permission_key):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing required permission: {permission_key}")
        if _live_check_enabled():
            # A token can outlive a revocation by up to 12 hours; Management data cannot.
            live = _live_permissions(claims.user_id)
            if live is None:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Access could not be confirmed. Please try again.")
            if PERM_MANAGEMENT_ACCESS not in live or permission_key not in live:
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing required permission: {permission_key}")
        return claims

    return _dependency
