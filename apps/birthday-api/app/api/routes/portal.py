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

Fulfilment lifecycle (plan §O): Acknowledge + Confirm are merged into a
single ``accept`` action — the old two-step "acknowledge, then confirm"
carried no information between the steps. ``DELIVERED`` immediately
auto-completes (system actor) once the supplier marks it delivered.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import SupplierScope, require_supplier_permission
from app.core.constants import ActorType, OrderIssueStatus, OrderStatus
from app.db.session import get_db
from app.models.birthday_order import BirthdayOrder
from app.models.order_event import OrderEvent
from app.models.order_issue import OrderIssue
from app.repositories.birthday_order_repository import BirthdayOrderRepository
from app.schemas.order import (
    OrderIssueCreate,
    OrderIssueRead,
    SupplierOrderListResponse,
    SupplierOrderView,
    SupplierStatusUpdateRequest,
)
from app.services import order_status_service
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.order_service import to_supplier_view

router = APIRouter(prefix="/api/birthday/portal", tags=["birthday-supplier-portal"])

# Derived from order_status_service.SUPPLIER_DRIVABLE / ACTIONABLE — never
# a hand-mirrored second table (that duplication was flagged in the
# current-state review as a real drift risk).
_SUPPLIER_ALLOWED_TARGETS = order_status_service.SUPPLIER_DRIVABLE
_SUPPLIER_ACTIONABLE_STATUSES = order_status_service.SUPPLIER_ACTIONABLE_STATUSES

_STAGE_TIMESTAMP_FIELD = {
    OrderStatus.CONFIRMED: "accepted_at",
    OrderStatus.PREPARING: "preparing_at",
    OrderStatus.OUT_FOR_DELIVERY: "out_for_delivery_at",
    OrderStatus.DELIVERED: "delivered_at",
}


def _get_supplier_order_or_404(db: Session, order_id: int, scope: SupplierScope) -> BirthdayOrder:
    order = BirthdayOrderRepository(db).get_for_supplier(order_id, supplier_id=scope.supplier_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


@router.get("/dashboard")
def get_supplier_dashboard(
    db: Session = Depends(get_db),
    scope: SupplierScope = Depends(require_supplier_permission("birthday.portal.access")),
) -> dict:
    """Fulfilment-only, supplier-scoped dashboard (plan §N) — deliberately
    does not mirror the internal dashboard. Every count is scoped to this
    supplier's own orders via the same repository methods the order list
    uses, so isolation holds here too."""
    repo = BirthdayOrderRepository(db)
    today = date.today()

    def _count(*extra_where):
        stmt = select(func.count()).select_from(BirthdayOrder).where(
            BirthdayOrder.supplier_id == scope.supplier_id, *extra_where,
        )
        return db.execute(stmt).scalar_one()

    return {
        "new_orders": _count(BirthdayOrder.status == OrderStatus.SENT_TO_SUPPLIER.value),
        "due_today": _count(
            BirthdayOrder.delivery_date == today,
            BirthdayOrder.status.notin_([OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value]),
        ),
        "due_tomorrow": _count(
            BirthdayOrder.delivery_date == today.fromordinal(today.toordinal() + 1),
            BirthdayOrder.status.notin_([OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value]),
        ),
        "overdue": _count(
            BirthdayOrder.delivery_date < today,
            BirthdayOrder.status.notin_([OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value]),
        ),
        "out_for_delivery": _count(BirthdayOrder.status == OrderStatus.OUT_FOR_DELIVERY.value),
        "open_issues": db.execute(
            select(func.count()).select_from(OrderIssue).join(BirthdayOrder).where(
                BirthdayOrder.supplier_id == scope.supplier_id, OrderIssue.status == OrderIssueStatus.OPEN.value,
            )
        ).scalar_one(),
        "completed_today": _count(
            BirthdayOrder.status == OrderStatus.COMPLETED.value,
            func.date(BirthdayOrder.completed_at) == today,
        ),
    }


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
    page_size = max(1, min(page_size, 50))  # tightened from 200 — plan §U rate/volume hygiene
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


@router.post("/orders/{order_id}/accept", response_model=SupplierOrderView)
def accept_order(
    order_id: int,
    db: Session = Depends(get_db),
    scope: SupplierScope = Depends(require_supplier_permission("birthday.portal.respond")),
) -> SupplierOrderView:
    """Merged acknowledge+confirm (plan §O): one commitment, one click.
    SENT_TO_SUPPLIER -> CONFIRMED directly."""
    order = _get_supplier_order_or_404(db, order_id, scope)
    try:
        order = order_status_service.transition(
            db, order, OrderStatus.CONFIRMED,
            actor_id=scope.supplier_user_id, actor_type=ActorType.SUPPLIER,
            detail="Accepted by supplier",
        )
    except order_status_service.InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    order.accepted_at = datetime.now(UTC)
    db.commit()
    db.refresh(order)
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

    stamp_field = _STAGE_TIMESTAMP_FIELD.get(target)
    if stamp_field:
        setattr(order, stamp_field, datetime.now(UTC))
        db.commit()
        db.refresh(order)

    if target == OrderStatus.DELIVERED:
        # Auto-completion (plan §F/§L) — no internal button exists for
        # this on purpose; the moment the supplier marks it delivered the
        # order is done.
        order = order_status_service.auto_complete(db, order)

    return to_supplier_view(order)


@router.post(
    "/orders/{order_id}/issues", response_model=OrderIssueRead, status_code=status.HTTP_201_CREATED,
)
def raise_supplier_issue(
    order_id: int,
    payload: OrderIssueCreate,
    db: Session = Depends(get_db),
    scope: SupplierScope = Depends(require_supplier_permission("birthday.portal.respond")),
) -> OrderIssue:
    """Typed problem report (plan §O/§U) — replaces the old free-text-only
    /issue signal with a structured, resolvable record. Does not force a
    status change; an internal admin decides the resolution (reassign
    supplier, cancel, etc.), except CANNOT_FULFIL which flips the order to
    UNABLE_TO_FULFIL immediately since it always needs internal
    reassignment."""
    order = _get_supplier_order_or_404(db, order_id, scope)
    if OrderStatus(order.status) not in _SUPPLIER_ACTIONABLE_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"An issue can only be raised while an order is in progress "
            f"(current status: {order.status})",
        )
    issue = OrderIssue(
        order_id=order.id, raised_by_type="SUPPLIER", raised_by_id=scope.supplier_user_id,
        type=payload.type, detail=payload.detail, status=OrderIssueStatus.OPEN.value,
    )
    db.add(issue)
    db.add(
        OrderEvent(
            order_id=order.id, event_type="SUPPLIER_ISSUE", actor_id=scope.supplier_user_id,
            actor_type=ActorType.SUPPLIER.value, detail=f"[{payload.type}] {payload.detail}",
        )
    )

    if payload.type == "CANNOT_FULFIL":
        try:
            order = order_status_service.transition(
                db, order, OrderStatus.UNABLE_TO_FULFIL,
                actor_id=scope.supplier_user_id, actor_type=ActorType.SUPPLIER,
                detail=payload.detail,
            )
        except order_status_service.InvalidTransitionError:
            pass

    db.commit()
    db.refresh(issue)

    try:
        AuditService().log(
            actor_id=scope.supplier_user_id, action="birthday.order.supplier_issue",
            entity_type="birthday_order", entity_id=order.id,
            metadata={"type": payload.type, "detail": payload.detail},
        )
    except Exception:  # noqa: BLE001 - best-effort
        pass

    try:
        NotificationService().notify_module_role(
            module_key="birthday", role="BIRTHDAY_ADMIN", type="birthday.supplier_issue",
            title=f"Supplier reported a problem on {order.order_reference}",
            body=f"[{payload.type}] {payload.detail}",
            related_entity_type="birthday_order", related_entity_id=order.id,
        )
    except Exception:  # noqa: BLE001 - best-effort
        pass

    return issue


@router.get("/orders/{order_id}/issues", response_model=list[OrderIssueRead])
def list_supplier_order_issues(
    order_id: int,
    db: Session = Depends(get_db),
    scope: SupplierScope = Depends(require_supplier_permission("birthday.portal.access")),
) -> list[OrderIssue]:
    order = _get_supplier_order_or_404(db, order_id, scope)
    return list(order.issues)
