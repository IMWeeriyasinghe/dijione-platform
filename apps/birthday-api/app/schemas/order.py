from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class OrderEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    from_status: str | None
    to_status: str | None
    actor_id: int | None
    actor_type: str
    detail: str | None
    created_at: datetime


class SpecialRequirementCreate(BaseModel):
    kind: str
    text: str


class SpecialRequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    kind: str
    text: str
    created_by: int | None
    created_at: datetime


class BirthdayOrderSummary(BaseModel):
    """Lighter list-view shape — no nested events/special_requirements."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_reference: str
    employee_id: str
    employee_number: str | None = None
    employee_name: str
    birthday_date: date
    birthday_year: int
    office_location: str
    lead_time_class: str
    status: str
    supplier_id: int | None
    supplier_name: str | None = None
    delivery_date: date | None = None
    catalogue_item_id: int | None = None
    requires_admin_review: bool
    exception_reason: str | None = None
    verify_by: date | None = None
    address_verification_status: str


class BirthdayOrderRead(BaseModel):
    """Note: delivery_address_* fields below are the internal (P&C-facing)
    view — always populated once known, regardless of verification status.
    The supplier-facing equivalent (SupplierOrderView) only ever exposes
    them once VERIFIED — see order_service.to_supplier_view."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_reference: str
    employee_id: str
    employee_number: str | None = None
    employee_name: str
    employee_email: str
    birthday_date: date
    birthday_year: int
    office_location: str
    detected_at: datetime | None
    lead_time_days: int
    lead_time_class: str
    quantity: int
    status: str
    hold_reason: str | None
    address_verification_status: str
    delivery_address_line1: str | None = None
    delivery_address_line2: str | None = None
    delivery_city: str | None = None
    delivery_state_province: str | None = None
    delivery_postal_code: str | None = None
    delivery_country: str | None = None
    delivery_address_source: str | None = None
    supplier_id: int | None
    supplier_name: str | None = None
    delivery_date: date | None = None
    catalogue_item_id: int | None = None
    is_manual_override: bool
    requires_admin_review: bool
    exception_reason: str | None = None
    verify_by: date | None = None
    retry_count: int
    last_failure_reason: str | None
    released_at: datetime | None = None
    released_by: int | None = None
    review_confirmed_at: datetime | None = None
    review_confirmed_by: int | None = None
    accepted_at: datetime | None = None
    preparing_at: datetime | None = None
    out_for_delivery_at: datetime | None = None
    delivered_at: datetime | None = None
    completed_at: datetime | None = None
    created_by: int | None
    created_at: datetime
    updated_at: datetime
    events: list[OrderEventRead] = []
    special_requirements: list[SpecialRequirementRead] = []
    issues: list[OrderIssueRead] = []


class BirthdayOrderCreate(BaseModel):
    employee_id: str
    employee_number: str | None = None
    employee_name: str
    employee_email: str
    birthday_date: date
    office_location: str
    quantity: int = 1
    # Optional — defaults server-side to the birthday occurrence (§8).
    delivery_date: date | None = None
    special_requirements: list[SpecialRequirementCreate] = []


class BirthdayOrderUpdate(BaseModel):
    """Partial/PATCH-able non-status fields only — status changes always go
    through the dedicated hold/release/cancel endpoints and
    ``order_status_service``."""

    quantity: int | None = None
    hold_reason: str | None = None
    office_location: str | None = None
    supplier_id: int | None = None
    delivery_date: date | None = None
    catalogue_item_id: int | None = None


class HoldRequest(BaseModel):
    hold_reason: str


class ReleaseRequest(BaseModel):
    note: str | None = None


class CancelRequest(BaseModel):
    reason: str | None = None


class VerifyAddressRequest(BaseModel):
    """The one routine human checkpoint (plan §J/§K). ``corrected=True``
    tells the verify service the address was edited, not just confirmed as
    snapshotted — a correction always flags the order for review rather
    than auto-releasing it."""

    corrected: bool = False
    note: str | None = None


class ConfirmReleaseRequest(BaseModel):
    """One-click release for a REQUIRES_REVIEW (flagged) order."""

    note: str | None = None


class VerifyAddressResponse(BaseModel):
    order: BirthdayOrderRead
    auto_released: bool
    flagged_reasons: list[str] = []


class OrderIssueCreate(BaseModel):
    type: str
    detail: str


class OrderIssueResolve(BaseModel):
    resolution_detail: str


class OrderIssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    raised_by_type: str
    raised_by_id: int | None
    type: str
    detail: str
    status: str
    resolution_detail: str | None = None
    resolved_by: int | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class ReadinessCheckResponse(BaseModel):
    ready: bool
    missing: list[str] = []


class BirthdayOrderListResponse(BaseModel):
    """Stable paginated envelope (Phase-Next §4) — replaces the old bare
    list response so the frontend can render real page controls instead of
    a "disable Next by heuristic" guess."""

    items: list[BirthdayOrderSummary]
    total: int
    page: int
    page_size: int


class OrderConflict(BaseModel):
    """409 response body when a manual create collides with an existing
    employee_id+birthday_year order."""

    detail: str
    existing_order: BirthdayOrderSummary


class AddressVerificationUpdate(BaseModel):
    status: str
    note: str | None = None


class DeliveryAddressUpdate(BaseModel):
    """P&C-manual correction of the delivery address snapshot (plan §3D/G)
    — does not change address_verification_status; callers typically PATCH
    this and then separately PATCH address-verification to VERIFIED."""

    delivery_address_line1: str | None = None
    delivery_address_line2: str | None = None
    delivery_city: str | None = None
    delivery_state_province: str | None = None
    delivery_postal_code: str | None = None
    delivery_country: str | None = None


class SupplierOrderView(BaseModel):
    """What a supplier is allowed to see (plan §6) — fulfilment facts only,
    deliberately NOT the full ``BirthdayOrderRead``/``Summary`` shape: no
    HR eligibility logic, hire dates, termination dates, employment
    status, eligibility reasons, INTERNAL_NOTE-kind requirements, or any
    other supplier's data ever cross into this DTO — fields are only ever
    selected into this model, never filtered out of a richer one, so a
    future field added to the internal schema cannot leak here by
    accident. ``employee_name`` is intentionally the recipient's full
    display name (needed for cake personalization / delivery matching —
    not treated as sensitive on its own)."""

    model_config = ConfigDict(from_attributes=False)

    id: int
    order_reference: str
    employee_name: str
    birthday_date: date
    delivery_date: date | None = None
    office_location: str
    quantity: int
    catalogue_item_name: str | None = None
    address_verified: bool
    # Only ever populated once address_verified is True — see
    # order_service.to_supplier_view. Never the raw/unverified snapshot.
    delivery_address_line1: str | None = None
    delivery_address_line2: str | None = None
    delivery_city: str | None = None
    delivery_state_province: str | None = None
    delivery_postal_code: str | None = None
    delivery_country: str | None = None
    status: str
    special_instructions: list[str] = []


class SupplierOrderListResponse(BaseModel):
    items: list[SupplierOrderView]
    total: int
    page: int
    page_size: int


class SupplierStatusUpdateRequest(BaseModel):
    status: str


class SupplierIssueRequest(BaseModel):
    """Legacy free-text-only issue payload — superseded by OrderIssueCreate
    (typed) but kept so any existing caller of POST /portal/orders/{id}/issue
    still works during the transition."""

    detail: str


BirthdayOrderRead.model_rebuild()
VerifyAddressResponse.model_rebuild()
