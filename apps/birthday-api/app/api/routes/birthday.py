"""DijiBirthday service skeleton (CR §9, §36, §51).

This phase proves DijiOne can host a second independently bounded
application, not the Birthday workflow itself: no BambooHR connection, no
cake-ordering logic, no database. Real functionality (birthday detection,
duplicate prevention, supplier ordering, failure tracking) lands in a later
phase, on top of exactly this skeleton — metadata/summary contract, module
registry entry (COMING_SOON), and the same claims-based auth seam every
other DijiOne service uses.
"""

from auth_client_py import AuthClaims
from fastapi import APIRouter, Depends

from app.api.deps import get_claims

router = APIRouter(prefix="/api/birthday", tags=["birthday"])


@router.get("/metadata")
def metadata() -> dict:
    return {
        "key": "birthday",
        "name": "DijiBirthday",
        "description": "Birthday Workflow Automation",
        "product_status": "COMING_SOON",
    }


@router.get("/summary")
def summary() -> dict:
    """DijiOne Home's per-module status card (CR §15, §18) — distinguishes
    product status (COMING_SOON, set here) from runtime health (this
    service being reachable at all, which the caller already knows if this
    response came back)."""
    return {"service": "birthday-api", "status": "healthy", "product_status": "COMING_SOON"}


@router.get("/whoami")
def whoami(claims: AuthClaims = Depends(get_claims)) -> dict:
    """Proves the Platform Core authorization seam decodes real claims end
    to end — not wired to any actual permission check yet since there is no
    birthday-flow business capability to gate."""
    return {"user_id": claims.user_id, "full_name": claims.full_name}
