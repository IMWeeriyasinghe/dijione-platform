"""Frontend-facing DTOs for the "upcoming birthdays" employee directory
view — distinct from ``app/schemas/order.py``'s ``BirthdayOrderSummary``.

This view is computed directly from BambooHR's active-employee roster (not
from ``BirthdayOrder`` rows), so it also surfaces employees whose birthday
hasn't been scanned/ordered yet. ``cake_order_status`` reports the linked
order's status when one exists, or the stub value ``"not_created"``
otherwise — no cake-ordering workflow is triggered by this endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class UpcomingBirthdayItem(BaseModel):
    employee_id: str  # BambooHR internal record id — secondary/internal identifier
    employee_number: str | None = None  # business Employee ID (BambooHR employeeNumber) — primary display field
    display_name: str
    birthday: str  # MM-DD, no birth year (BambooHR withholds birth year)
    days_until_birthday: int
    department: str
    location: str
    cake_order_status: str
    hire_date: str | None = None  # ISO date, None if genuinely missing from BambooHR
    eligible: bool
    eligibility_reason: str  # EligibilityReason value — always present, ELIGIBLE when eligible=True
    address_verification_status: str | None = None  # None when no order exists yet (nothing to verify)


class UpcomingBirthdaysResponse(BaseModel):
    days: int
    birthdays: list[UpcomingBirthdayItem]
    total: int
    page: int
    page_size: int
