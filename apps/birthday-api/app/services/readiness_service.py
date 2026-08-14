"""Readiness check for the approval workflow (Phase-Next §2). An order is
"ready for approval" once every mandatory fulfilment fact is present.
Employee eligibility is deliberately NOT re-checked here: an ineligible
employee never gets a ``BirthdayOrder`` row in the first place
(``detection_service.run_daily_scan`` only creates orders for eligible
employees), so by the time a row exists, eligibility is already satisfied.

Used both by the auto-promotion step (DRAFT -> READY_FOR_APPROVAL) and by
the manual ``submit-for-approval``/``approve`` endpoints, which always
re-validate server-side rather than trusting a client-supplied "looks
ready" flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.constants import AddressVerificationStatus
from app.models.birthday_order import BirthdayOrder


@dataclass
class ReadinessResult:
    ready: bool
    missing: list[str] = field(default_factory=list)


def check(order: BirthdayOrder) -> ReadinessResult:
    missing: list[str] = []

    if order.address_verification_status != AddressVerificationStatus.VERIFIED.value:
        missing.append("address_not_verified")
    if order.supplier_id is None:
        missing.append("supplier_not_assigned")
    if not order.office_location:
        missing.append("office_location_missing")
    if not order.quantity or order.quantity < 1:
        missing.append("quantity_invalid")
    if not order.employee_name:
        missing.append("employee_name_missing")

    return ReadinessResult(ready=not missing, missing=missing)
