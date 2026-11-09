"""DijiAtWork module foundation: metadata, status and caller identity only.

Attendance, employee linking and administration are later stages.
"""

from auth_client_py import AuthClaims
from fastapi import APIRouter, Depends

from app.api.deps import get_claims, require_atwork_permission
from app.core.constants import MODULE_ATWORK, PERM_MANAGEMENT_ACCESS, SERVICE_NAME
from app.schemas.atwork import AtworkMeOut

router = APIRouter(prefix="/api/atwork", tags=["atwork"])


@router.get("/metadata")
def metadata() -> dict:
    return {
        "key": MODULE_ATWORK,
        "name": "DijiAtWork",
        "description": "Employee work check-in and attendance",
        "product_status": "COMING_SOON",
    }


@router.get("/summary")
def summary() -> dict:
    """DijiOne Home's per-module status card."""
    return {"service": SERVICE_NAME, "status": "healthy", "product_status": "COMING_SOON"}


@router.get("/me", response_model=AtworkMeOut)
def me(claims: AuthClaims = Depends(get_claims)) -> AtworkMeOut:
    """A valid token without a DijiAtWork role gets ``module_access=false``,
    so the UI can explain the situation; it carries no permissions."""
    module_claim = claims.module(MODULE_ATWORK)
    return AtworkMeOut(
        user_id=claims.user_id,
        full_name=claims.full_name,
        module_access=module_claim is not None,
        role=module_claim.role if module_claim else None,
        permissions=sorted(module_claim.permissions) if module_claim else [],
    )


@router.get("/management/access")
def management_access(_claims: AuthClaims = Depends(require_atwork_permission(PERM_MANAGEMENT_ACCESS))) -> dict:
    """Access check for the future Management area; it returns no business data."""
    return {"allowed": True}
