"""Supplier-portal API surface (Phase-Next §5) — consumed only by
``apps/birthday-supplier-web``, never by the internal ``birthday-web``.

Isolation is enforced entirely server-side: every route resolves
``supplier_id`` from ``SupplierScope`` (the validated token claim), never
from a URL/body parameter, and every repository call filters on it. A
manipulated order id belonging to a different supplier 404s — the caller
learns nothing about whether the id exists.

Response schemas (``SupplierOrderView``) are a genuinely separate Pydantic
model from the internal ``BirthdayOrderRead``/``Summary`` — HR fields
(hire date, termination date, employment status, eligibility reason,
INTERNAL_NOTE-kind requirements) are never selected into it in the first
place, not filtered out of a richer shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import SupplierScope, require_supplier_permission
from app.core.constants import ActorType, OrderStatus
from app.db.session import get_db
from app.models.birthday_order import BirthdayOrder
from app.models.order_event import OrderEvent
from app.repositories.birthday_order_repository import BirthdayOrderRepository
from app.schemas.order import (
    SupplierIssueRequest,
    SupplierOrderListResponse,
    SupplierOrderView,
    SupplierStatusUpdateRequest,
)
from app.services import order_status_service
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.order_service import to_supplier_view

router = APIRouter(prefix="/api/birthday/portal", tags=["birthday-supplier-portal"])

# Allow-listed status transitions a supplier user may perform directly
# (plan §6: acknowledge/accept/preparing/scheduled-ready/delivered/unable
# to fulfil). Anything else (e.g. jumping straight to COMPLETED) stays an
# internal-only action via order_status_service's full transition table.
_SUPPLIER_ALLOWED_TARGETS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.SUPPLIER_REVIEW: {
        OrderStatus.CONFIRMED, OrderStatus.CHANGE_REQUESTED, OrderStatus.UNABLE_TO_FULFIL,
    },
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING},
    OrderStatus.PREPARING: {OrderStatus.OUT_FOR_DELIVERY},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED},
}


def _get_supplier_order_or_404(db: Session, order_id: int, scope: SupplierScope) -> BirthdayOrder:
    order = BirthdayOrderRepository(db).get_for_supplier(order_id, supplier_id=scope.supplier_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


@router.get("/orders", response_model=SupplierOrderListResponse)
def list_supplier_orders(
    search: str | None = None,
    sort_by: str | None = None,
    sort_direction: str = "desc",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    scope: SupplierScope = Depends(require_supplier_permission("birthday.portal.access")),
) -> SupplierOrderListResponse:
    if sort_direction not in ("asc", "desc"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "sort_direction must be 'asc' or 'desc'")
    page = max(page, 1)
    page_size = max(1, min(page_size, 200))
    repo = BirthdayOrderRepository(db)
    orders = repo.list_for_supplier(
        supplier_id=scope.supplier_id, search=search, sort_by=sort_by, sort_direction=sort_direction,
        limit=page_size, offset=(page - 1) * page_size,
    )
    total = repo.count_for_supplier(supplier_id=scope.supplier_id, search=search)
    return SupplierOrderListResponse(
        items=[to_supplier_view(o) for o in orders], total=total, page=page, page_size=page_size,
    )


@router.get("/orders/{order_id}", response_model=SupplierOrderView)
def get_supplier_order(
    order_id: int,
    db: Session = Depends(get_db),
    scope: SupplierScope = Depends(require_supplier_permission("birthday.portal.access")),
) -> SupplierOrderView:
    order = _get_supplier_order_or_404(db, order_id, scope)
    return to_supplier_view(order)


@router.post("/orders/{order_id}/acknowledge", response_model=SupplierOrderView)
def acknowledge_order(
    order_id: int,
    db: Session = Depends(get_db),
    scope: SupplierScope = Depends(require_supplier_permission("birthday.portal.respond")),
) -> SupplierOrderView:
    order = _get_supplier_order_or_404(db, order_id, scope)
    try:
        order = order_status_service.transition(
            db, order, OrderStatus.SUPPLIER_REVIEW,
            actor_id=scope.supplier_user_id, actor_type=ActorType.SUPPLIER,
            detail="Acknowledged by supplier",
        )
    except order_status_service.InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return to_supplier_view(order)


@router.patch("/orders/{order_id}/status", response_model=SupplierOrderView)
def update_supplier_order_status(
    order_id: int,
    payload: SupplierStatusUpdateRequest,
    db: Session = Depends(get_db),
    scope: SupplierScope = Depends(require_supplier_permission("birthday.portal.respond")),
) -> SupplierOrderView:
    order = _get_supplier_order_or_404(db, order_id, scope)
    try:
        target = OrderStatus(payload.status)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid status: {payload.status!r}") from exc

    current = OrderStatus(order.status)
    allowed = _SUPPLIER_ALLOWED_TARGETS.get(current, set())
    if target not in allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Supplier users may not set status to {target.value} from {current.value}",
        )
    try:
        order = order_status_service.transition(
            db, order, target, actor_id=scope.supplier_user_id, actor_type=ActorType.SUPPLIER,
        )
    except order_status_service.InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return to_supplier_view(order)


@router.post("/orders/{order_id}/issue", response_model=SupplierOrderView)
def raise_supplier_issue(
    order_id: int,
    payload: SupplierIssueRequest,
    db: Session = Depends(get_db),
    scope: SupplierScope = Depends(require_supplier_permission("birthday.portal.respond")),
) -> SupplierOrderView:
    """Records an issue without forcing a status change — an internal
    admin decides the resolution (reassign supplier, cancel, etc.)."""
    order = _get_supplier_order_or_404(db, order_id, scope)
    db.add(
        OrderEvent(
            order_id=order.id,
            event_type="SUPPLIER_ISSUE",
            actor_id=scope.supplier_user_id,
            actor_type=ActorType.SUPPLIER.value,
            detail=payload.detail,
        )
    )
    db.commit()
    db.refresh(order)

    try:
        AuditService().log(
            actor_id=scope.supplier_user_id, action="birthday.order.supplier_issue",
            entity_type="birthday_order", entity_id=order.id, metadata={"detail": payload.detail},
        )
    except Exception:  # noqa: BLE001 - best-effort
        pass

    try:
        NotificationService().notify_module_role(
            module_key="birthday", role="BIRTHDAY_ADMIN", type="birthday.supplier_issue",
            title=f"Supplier reported an issue on {order.order_reference}",
            body=payload.detail, related_entity_type="birthday_order", related_entity_id=order.id,
        )
    except Exception:  # noqa: BLE001 - best-effort
        pass

    return to_supplier_view(order)
