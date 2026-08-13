"""DijiSpark service skeleton (CR §10, §36, §51).

This phase proves DijiOne can host a third independently bounded
application, not the Spark workflow itself: no Spark Hire integration, no
BambooHR report upload, no database. Real functionality (candidate report
retrieval, hiring/coaching workflows, integration processing status) lands
in a later phase, on top of exactly this skeleton — metadata/summary
contract, module registry entry (COMING_SOON), and the same claims-based
auth seam every other DijiOne service uses.
"""

from auth_client_py import AuthClaims
from fastapi import APIRouter, Depends

from app.api.deps import get_claims

router = APIRouter(prefix="/api/spark", tags=["spark"])


@router.get("/metadata")
def metadata() -> dict:
    return {
        "key": "spark",
        "name": "DijiSpark",
        "description": "HR / Spark Hire Workflows",
        "product_status": "COMING_SOON",
    }


@router.get("/summary")
def summary() -> dict:
    """DijiOne Home's per-module status card (CR §15, §18)."""
    return {"service": "spark-api", "status": "healthy", "product_status": "COMING_SOON"}


@router.get("/whoami")
def whoami(claims: AuthClaims = Depends(get_claims)) -> dict:
    """Proves the Platform Core authorization seam decodes real claims end
    to end — not wired to any actual permission check yet since there is no
    spark-flow business capability to gate."""
    return {"user_id": claims.user_id, "full_name": claims.full_name}
