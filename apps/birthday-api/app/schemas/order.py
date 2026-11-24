from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.core.greeting import GREETING_MAX_LENGTH, default_greeting_for, normalise_greeting

# Accepts numbers as people write them (+94 77 123 4567, (011) 234-5678).
# Validation only: the value is stored exactly as entered, never reformatted.
_PHONE_PATTERN = re.compile(r"\+?[0-9][0-9 ()\-.]{4,40}")


class OrderEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    from_status: str | None
    to_status: str | None
    actor_id: int | None
    actor_type: str
    actor_display_name: str | None = None
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
    employee_mobile_phone: str | None = None
    employee_home_phone: str | None = None
    delivery_contact_phone: str | None = None
    birthday_greeting: str | None = None
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def suggested_birthday_greeting(self) -> str:
        """What the default greeting would be. Shown (not saved) for a legacy
        order whose greeting is still NULL, so P&C can adopt or edit it;
        never overwrites a stored greeting."""
        return default_greeting_for(self.employee_email, self.employee_name)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def contact_refreshable(self) -> bool:
        """True when "Refresh contact from People" can safely fill a missing
        contact snapshot: unreleased, identifiable, something still empty."""
        return (
            self.released_at is None
            and bool((self.employee_id or "").strip())
            and not ((self.employee_mobile_phone or "").strip() and (self.employee_home_phone or "").strip())
        )


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
    # Supplying this on an order flagged MISSING_EMPLOYEE_NUMBER clears the
    # exception and (while the order has never reached a supplier)
    # regenerates the provisional BDAY-TMP… reference to BDAY-EMP…
    employee_number: str | None = None
    # P&C-edited birthday greeting (multi-line). An empty value clears it so
    # no greeting is sent; the stored text is never regenerated afterwards.
    birthday_greeting: str | None = Field(default=None, max_length=GREETING_MAX_LENGTH)

    @field_validator("birthday_greeting")
    @classmethod
    def _clean_greeting(cls, value: str | None) -> str | None:
        return None if value is None else normalise_greeting(value)


class HoldRequest(BaseModel):
    hold_reason: str


class ReleaseRequest(BaseModel):
    note: str | None = None


class CancelRequest(BaseModel):
    reason: str | None = None


class ReopenRequest(BaseModel):
    # Mandatory, unlike CancelRequest's optional reason — Phase 1.6 §14
    # requires an explicit, non-empty reason for every reopen.
    reason: str


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


class OrderMessageCreate(BaseModel):
    """A Portal message on an order (Phase 1 §G flows 1 & 2)."""

    body: str
    issue_id: int | None = None
    # Internal only: also send an email copy so the supplier is nudged to
    # check the portal (the portal has no push in Phase 1).
    also_email: bool = False


class TimelineEntryOut(BaseModel):
    at: datetime | None
    kind: str
    channel: str | None = None
    direction: str | None = None
    author_type: str | None = None
    author_id: int | None = None
    title: str
    body: str | None = None
    meta: dict = {}
    body_format: str = "text"
    subject: str | None = None


class OrderTimelineResponse(BaseModel):
    order_id: int
    order_reference: str
    entries: list[TimelineEntryOut] = []


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
    # The number the supplier should call. Changing it is not an address
    # correction, so it never flags the order for review.
    delivery_contact_phone: str | None = Field(default=None, max_length=64)

    @field_validator("delivery_contact_phone")
    @classmethod
    def _clean_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if value and not _PHONE_PATTERN.fullmatch(value):
            raise ValueError("Enter a phone number using digits, spaces, +, -, ( or )")
        return value or None


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


class SupplierOrderDetailView(SupplierOrderView):
    """Single-order view for the assigned supplier: adds the team member's
    delivery contact numbers. Only ever returned by the order-detail route,
    never by list endpoints, and only populated once the address is
    verified (same rule as the delivery address)."""

    delivery_contact_phone: str | None = None
    alternative_contact_phone: str | None = None
    # The birthday message P&C released with the order (read-only for the
    # supplier; line breaks preserved).
    birthday_greeting: str | None = None


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
