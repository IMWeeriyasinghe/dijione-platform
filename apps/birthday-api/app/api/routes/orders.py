"""Cake Orders register — BirthdayScope-gated per plan §6. All status
mutation goes through ``order_status_service`` — never a direct ``status``
assignment here."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import BirthdayScope, require_birthday_permission
from app.api.routes.config import get_or_create_config
from app.core.constants import AddressVerificationStatus, OrderIssueStatus, OrderStatus
from app.db.session import get_db
from app.models.birthday_order import BirthdayOrder
from app.models.order_event import OrderEvent
from app.models.order_issue import OrderIssue
from app.models.special_requirement import SpecialRequirement
from app.models.supplier import Supplier
from app.models.supplier_communication import SupplierCommunication
from app.repositories.birthday_order_repository import BirthdayOrderRepository
from app.schemas.order import (
    AddressVerificationUpdate,
    BirthdayOrderCreate,
    BirthdayOrderListResponse,
    BirthdayOrderRead,
    BirthdayOrderSummary,
    BirthdayOrderUpdate,
    CancelRequest,
    ConfirmReleaseRequest,
    DeliveryAddressUpdate,
    HoldRequest,
    OrderIssueCreate,
    OrderIssueRead,
    OrderIssueResolve,
    ReadinessCheckResponse,
    ReleaseRequest,
    SpecialRequirementCreate,
    SpecialRequirementRead,
    VerifyAddressRequest,
    VerifyAddressResponse,
)
from app.services import (
    address_verification_service,
    detection_service,
    order_email_service,
    order_status_service,
    readiness_service,
)
from app.services.audit_service import AuditService
from app.services.order_sequence_service import next_order_reference
from app.services.order_service import create_or_get_order

router = APIRouter(prefix="/api/birthday/orders", tags=["birthday-orders"])


def _get_order_or_404(db: Session, order_id: int) -> BirthdayOrder:
    order = BirthdayOrderRepository(db).get_by_id(order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


_SORT_DIRECTIONS = {"asc", "desc"}


@router.get("", response_model=BirthdayOrderListResponse)
def list_orders(
    search: str | None = None,
    status_filter: str | None = None,
    lead_time_class: str | None = None,
    office_location: str | None = None,
    supplier_id: int | None = None,
    address_verification_status: str | None = None,
    sort_by: str | None = None,
    sort_direction: str = "desc",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.read")),
) -> BirthdayOrderListResponse:
    if sort_direction not in _SORT_DIRECTIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "sort_direction must be 'asc' or 'desc'")
    page = max(page, 1)
    page_size = max(1, min(page_size, 200))
    repo = BirthdayOrderRepository(db)
    filters = dict(
        status=status_filter, lead_time_class=lead_time_class,
        office_location=office_location, supplier_id=supplier_id,
        search=search, address_verification_status=address_verification_status,
    )
    items = repo.list_filtered(
        **filters, sort_by=sort_by, sort_direction=sort_direction,
        limit=page_size, offset=(page - 1) * page_size,
    )
    total = repo.count_filtered(**filters)
    return BirthdayOrderListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{order_id}", response_model=BirthdayOrderRead)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.read")),
) -> BirthdayOrder:
    return _get_order_or_404(db, order_id)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BirthdayOrderRead)
def create_order(
    payload: BirthdayOrderCreate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.create")),
) -> BirthdayOrder:
    """Manual admin creation. Unlike the automated scan's silent
    idempotent dedup, a manual duplicate is surfaced as 409 with the
    existing order's reference rather than silently returned."""
    birthday_year = payload.birthday_date.year
    repo = BirthdayOrderRepository(db)
    existing = repo.get_by_employee_and_year(payload.employee_id, birthday_year)
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "detail": (
                    f"An order already exists for employee {payload.employee_id} in "
                    f"{birthday_year}: {existing.order_reference}"
                ),
                "existing_order": BirthdayOrderSummary.model_validate(existing).model_dump(mode="json"),
            },
        )

    # Business-facing Team Member ID (BambooHR employeeNumber), NOT the
    # internal record id — falls back to the internal id only when the
    # employee genuinely has no employeeNumber. See order_sequence_service.
    team_member_id = payload.employee_number or payload.employee_id
    order_reference = next_order_reference(db, team_member_id, birthday_year)
    # Deterministic supplier default (§5/§6): sole ACTIVE supplier ->
    # office-location rule -> is_default. Still fully editable afterwards.
    default_supplier = detection_service.resolve_supplier_for_office(payload.office_location, db)
    order, _created = create_or_get_order(
        db,
        employee_id=payload.employee_id,
        employee_number=payload.employee_number,
        employee_name=payload.employee_name,
        employee_email=payload.employee_email,
        order_reference=order_reference,
        birthday_date=payload.birthday_date,
        birthday_year=birthday_year,
        # §8: delivery date defaults to the birthday occurrence.
        delivery_date=payload.delivery_date or payload.birthday_date,
        office_location=payload.office_location,
        lead_time_days=(payload.birthday_date - date.today()).days,
        lead_time_class="NORMAL",
        status=OrderStatus.PENDING_VERIFICATION,
        requires_admin_review=False,
        hold_reason=None,
        supplier_id=default_supplier.id if default_supplier is not None else None,
    )
    order.quantity = payload.quantity
    order.is_manual_override = True
    order.created_by = scope.user.id

    for req in payload.special_requirements:
        db.add(SpecialRequirement(order_id=order.id, kind=req.kind, text=req.text, created_by=scope.user.id))

    db.commit()
    db.refresh(order)

    try:
        AuditService().log(
            actor_id=scope.user.id, action="birthday.order.create", entity_type="birthday_order",
            entity_id=order.id, new_state={"order_reference": order.order_reference},
        )
    except Exception:  # noqa: BLE001 - best-effort
        pass

    return order


@router.patch("/{order_id}", response_model=BirthdayOrderRead)
def update_order(
    order_id: int,
    payload: BirthdayOrderUpdate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.update")),
) -> BirthdayOrder:
    order = _get_order_or_404(db, order_id)
    updates = payload.model_dump(exclude_unset=True)
    supplier_reassigned = "supplier_id" in updates and updates["supplier_id"] != order.supplier_id
    date_changed = "delivery_date" in updates and updates["delivery_date"] != order.delivery_date
    if supplier_reassigned and updates["supplier_id"] is not None:
        target_supplier = db.get(Supplier, updates["supplier_id"])
        if target_supplier is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found")
        if target_supplier.status != "ACTIVE":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Supplier {target_supplier.name!r} is INACTIVE and cannot be assigned to orders",
            )
    # Already visible to the supplier — a change here must not be silent
    # (plan §Y). Flag for a fresh human look and notify.
    was_supplier_visible = order.status in order_status_service.SUPPLIER_VISIBLE_STATUSES
    for field, value in updates.items():
        setattr(order, field, value)
    if supplier_reassigned:
        db.add(
            OrderEvent(
                order_id=order.id,
                event_type="SUPPLIER_ASSIGNED",
                actor_id=scope.user.id,
                actor_type="USER",
                detail=f"Supplier reassigned to supplier_id={updates.get('supplier_id')}",
            )
        )
    if (supplier_reassigned or date_changed) and was_supplier_visible:
        db.add(
            OrderEvent(
                order_id=order.id,
                event_type="ORDER_CHANGED_POST_RELEASE",
                actor_id=scope.user.id,
                actor_type="USER",
                detail=(
                    f"delivery_date changed to {updates.get('delivery_date')}"
                    if date_changed else f"supplier reassigned to supplier_id={updates.get('supplier_id')}"
                ),
            )
        )
        # NOTE: no supplier-facing push notification here — there is no
        # per-supplier notification channel yet (notify_module_role
        # broadcasts to every supplier, which would leak this order's
        # existence to unrelated suppliers). The OrderEvent above is
        # visible to the affected supplier the next time they load the
        # order; real supplier notifications are a deferred item pending
        # the Entra B2B / per-supplier notification work (see plan §U).
    db.commit()
    db.refresh(order)

    try:
        AuditService().log(
            actor_id=scope.user.id, action="birthday.order.update", entity_type="birthday_order",
            entity_id=order.id, new_state=updates,
        )
    except Exception:  # noqa: BLE001 - best-effort
        pass

    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: int,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.delete")),
) -> None:
    """Hard delete — PENDING_VERIFICATION-only, never-actioned orders.
    Every other order must be cancelled instead (non-destructive, preserves
    history); this is the real server-side boundary — the UI hiding the
    delete button is not sufficient (CLAUDE.md §7/§14)."""
    order = _get_order_or_404(db, order_id)
    if order.status != OrderStatus.PENDING_VERIFICATION.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only PENDING_VERIFICATION orders may be deleted (current status: {order.status}). "
            "Use cancel instead.",
        )
    has_communications = (
        db.query(SupplierCommunication).filter(SupplierCommunication.order_id == order.id).first()
        is not None
    )
    if has_communications:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Order has supplier communications on record and cannot be hard-deleted. Use cancel instead.",
        )

    try:
        AuditService().log(
            actor_id=scope.user.id, action="birthday.order.delete", entity_type="birthday_order",
            entity_id=order.id, previous_state={"status": order.status, "order_reference": order.order_reference},
        )
    except Exception:  # noqa: BLE001 - best-effort
        pass

    db.delete(order)
    db.commit()
    return None


@router.get("/{order_id}/readiness", response_model=ReadinessCheckResponse)
def check_readiness(
    order_id: int,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.read")),
) -> ReadinessCheckResponse:
    order = _get_order_or_404(db, order_id)
    result = readiness_service.check(order)
    return ReadinessCheckResponse(ready=result.ready, missing=result.missing)


@router.post("/{order_id}/verify", response_model=VerifyAddressResponse)
def verify_address(
    order_id: int,
    payload: VerifyAddressRequest,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.verify")),
) -> VerifyAddressResponse:
    """The one routine human checkpoint (plan §J/§K). Marking the address
    VERIFIED auto-releases a standard order to the supplier immediately —
    no separate submit/approve/send. A flagged order routes to
    REQUIRES_REVIEW instead; see /confirm-release."""
    order = _get_order_or_404(db, order_id)
    config = get_or_create_config(db)
    outcome = address_verification_service.verify_and_release(
        db, order, actor_id=scope.user.id, corrected=payload.corrected, note=payload.note, config=config,
    )
    return VerifyAddressResponse(
        order=outcome.order, auto_released=outcome.auto_released, flagged_reasons=outcome.flagged_reasons,
    )


@router.post("/{order_id}/confirm-release", response_model=BirthdayOrderRead)
def confirm_release(
    order_id: int,
    payload: ConfirmReleaseRequest,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.review")),
) -> BirthdayOrder:
    """One-click release for a REQUIRES_REVIEW (flagged) order — the
    exception-only approval (plan §K). Rejecting instead is a plain
    cancel with a reason."""
    order = _get_order_or_404(db, order_id)
    if OrderStatus(order.status) != OrderStatus.REQUIRES_REVIEW:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only REQUIRES_REVIEW orders can be confirmed & released (current status: {order.status})",
        )
    try:
        return address_verification_service.confirm_release(db, order, actor_id=scope.user.id)
    except order_email_service.NoSupplierAssignedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except order_email_service.AddressNotVerifiedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except order_email_service.NotReleasableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/{order_id}/hold", response_model=BirthdayOrderRead)
def hold_order(
    order_id: int,
    payload: HoldRequest,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.hold_release")),
) -> BirthdayOrder:
    order = _get_order_or_404(db, order_id)
    try:
        return order_status_service.hold(db, order, hold_reason=payload.hold_reason, actor_id=scope.user.id)
    except order_status_service.InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/{order_id}/release", response_model=BirthdayOrderRead)
def release_order(
    order_id: int,
    payload: ReleaseRequest,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.hold_release")),
) -> BirthdayOrder:
    order = _get_order_or_404(db, order_id)
    try:
        return order_status_service.release(db, order, actor_id=scope.user.id, note=payload.note)
    except order_status_service.InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/{order_id}/cancel", response_model=BirthdayOrderRead)
def cancel_order(
    order_id: int,
    payload: CancelRequest,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.cancel")),
) -> BirthdayOrder:
    order = _get_order_or_404(db, order_id)
    was_supplier_visible = order.status in order_status_service.SUPPLIER_VISIBLE_STATUSES
    try:
        order = order_status_service.cancel(db, order, actor_id=scope.user.id, reason=payload.reason)
    except order_status_service.InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    # NOTE: CANCELLED stays in SUPPLIER_VISIBLE_STATUSES (see
    # order_status_service.SUPPLIER_VISIBLE_STATUSES) so the portal shows a
    # tombstone with the cancellation reason instead of a silent 404 — the
    # fix for plan §Y's "internal->supplier changes must not be silent".
    # A push notification to just this supplier is deferred pending a
    # per-supplier notification channel (see note in update_order above).
    _ = was_supplier_visible
    return order


@router.post(
    "/{order_id}/special-requirements",
    response_model=SpecialRequirementRead,
    status_code=status.HTTP_201_CREATED,
)
def add_special_requirement(
    order_id: int,
    payload: SpecialRequirementCreate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.update")),
) -> SpecialRequirement:
    order = _get_order_or_404(db, order_id)
    requirement = SpecialRequirement(
        order_id=order.id, kind=payload.kind, text=payload.text, created_by=scope.user.id,
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


@router.get("/{order_id}/issues", response_model=list[OrderIssueRead])
def list_issues(
    order_id: int,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.read")),
) -> list[OrderIssue]:
    order = _get_order_or_404(db, order_id)
    return list(order.issues)


@router.post(
    "/{order_id}/issues", response_model=OrderIssueRead, status_code=status.HTTP_201_CREATED,
)
def raise_internal_issue(
    order_id: int,
    payload: OrderIssueCreate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.update")),
) -> OrderIssue:
    """Internal-raised issue — the same structured model the supplier
    portal writes into (plan §U). Consolidates what used to be three
    overlapping ad hoc signals into one typed, resolvable record."""
    order = _get_order_or_404(db, order_id)
    issue = OrderIssue(
        order_id=order.id, raised_by_type="USER", raised_by_id=scope.user.id,
        type=payload.type, detail=payload.detail, status=OrderIssueStatus.OPEN.value,
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue


@router.patch("/{order_id}/issues/{issue_id}/resolve", response_model=OrderIssueRead)
def resolve_issue(
    order_id: int,
    issue_id: int,
    payload: OrderIssueResolve,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.update")),
) -> OrderIssue:
    order = _get_order_or_404(db, order_id)
    issue = next((i for i in order.issues if i.id == issue_id), None)
    if issue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Issue not found")
    issue.status = OrderIssueStatus.RESOLVED.value
    issue.resolution_detail = payload.resolution_detail
    issue.resolved_by = scope.user.id
    from datetime import UTC, datetime

    issue.resolved_at = datetime.now(UTC)
    db.commit()
    db.refresh(issue)
    return issue


@router.patch("/{order_id}/address-verification", response_model=BirthdayOrderRead)
def update_address_verification(
    order_id: int,
    payload: AddressVerificationUpdate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.update")),
) -> BirthdayOrder:
    """P&C-manual only — never called by automation. No employee contact
    happens as a side effect of this call; P&C is expected to have already
    done their own outreach before setting VERIFIED/NEEDS_UPDATE here."""
    order = _get_order_or_404(db, order_id)
    try:
        new_status = AddressVerificationStatus(payload.status)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Invalid address verification status: {payload.status!r}",
        ) from exc
    return address_verification_service.set_address_verification_status(
        db, order, new_status, actor_id=scope.user.id, note=payload.note,
    )


@router.patch("/{order_id}/delivery-address", response_model=BirthdayOrderRead)
def update_delivery_address(
    order_id: int,
    payload: DeliveryAddressUpdate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.update")),
) -> BirthdayOrder:
    """P&C-manual correction of the delivery address (plan §3D/G) — does
    not change address_verification_status; the caller is expected to
    separately PATCH address-verification once the corrected address has
    been confirmed with the team member."""
    order = _get_order_or_404(db, order_id)
    return address_verification_service.update_delivery_address(
        db, order, payload.model_dump(exclude_unset=True), actor_id=scope.user.id,
    )


@router.post("/{order_id}/send-to-supplier", response_model=BirthdayOrderRead)
def send_to_supplier(
    order_id: int,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.send_supplier")),
) -> BirthdayOrder:
    order = _get_order_or_404(db, order_id)
    try:
        return order_email_service.send_order_to_supplier(db, order, actor_id=scope.user.id)
    except order_email_service.NoSupplierAssignedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except order_email_service.AddressNotVerifiedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except order_email_service.NotReleasableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except order_status_service.InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/{order_id}/resend", response_model=BirthdayOrderRead)
def resend_to_supplier(
    order_id: int,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.orders.send_supplier")),
) -> BirthdayOrder:
    order = _get_order_or_404(db, order_id)
    try:
        return order_email_service.resend_order_to_supplier(db, order, actor_id=scope.user.id)
    except order_email_service.NoSupplierAssignedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except order_email_service.AddressNotVerifiedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except order_email_service.NotReleasableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except order_status_service.InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
