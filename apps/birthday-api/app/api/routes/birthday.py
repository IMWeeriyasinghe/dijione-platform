"""DijiBirthday module metadata / summary / whoami surface.

These three endpoints back DijiOne Home's module card (``/metadata``,
``/summary``) and the shared claims-auth seam smoke check (``/whoami``).
The birthday workflow itself lives in the other route modules
(``orders``, ``suppliers``, ``portal``, ``employees``, ``admin``,
``internal``). ``/summary`` is intentionally unauthenticated, matching the
platform-wide module-summary convention (talent-api does the same) so the
shell can render the card before per-module auth resolves — it exposes
only three aggregate integer counts, no per-order data.
"""

from auth_client_py import AuthClaims
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_claims
from app.core.constants import OrderStatus
from app.db.session import get_db
from app.models.birthday_order import BirthdayOrder
from app.repositories.birthday_order_repository import BirthdayOrderRepository

router = APIRouter(prefix="/api/birthday", tags=["birthday"])

_EXCEPTION_STATUSES = {OrderStatus.REQUIRES_ATTENTION.value, OrderStatus.ON_HOLD.value}


@router.get("/metadata")
def metadata() -> dict:
    return {
        "key": "birthday",
        "name": "DijiBirthday",
        "description": "Birthday Workflow Automation",
        "product_status": "ACTIVE",
    }


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    """DijiOne Home's per-module status card (CR §15, §18) — distinguishes
    product status from runtime health (this service being reachable at
    all, which the caller already knows if this response came back).

    ``product_status`` is now hardcoded to ``"ACTIVE"`` as Phase C's real
    order-management surface exists — flipping the platform-api
    ``ApplicationModule`` registry row is a separate deployment step, not
    done here (out of birthday-api's scope)."""
    total_orders = db.execute(select(func.count()).select_from(BirthdayOrder)).scalar_one()
    exceptions_count = db.execute(
        select(func.count()).select_from(BirthdayOrder).where(BirthdayOrder.status.in_(_EXCEPTION_STATUSES))
    ).scalar_one()
    upcoming_count = len(BirthdayOrderRepository(db).list_upcoming(days_ahead=14))

    return {
        "service": "birthday-api",
        "status": "healthy",
        "product_status": "ACTIVE",
        "total_orders": total_orders,
        "exceptions_count": exceptions_count,
        "upcoming_count": upcoming_count,
    }


@router.get("/whoami")
def whoami(claims: AuthClaims = Depends(get_claims)) -> dict:
    """Smoke check that the Platform Core authorization seam decodes real
    claims end to end. The business endpoints enforce fine-grained
    permissions via ``require_birthday_permission`` / ``SupplierScope``."""
    return {"user_id": claims.user_id, "full_name": claims.full_name}
