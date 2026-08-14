"""Idempotent BambooHR-driven birthday detection: occurrence computation,
lead-time classification, scan-window filtering, supplier resolution, and
initial-status determination (CR §5/§10/§12).
"""

from __future__ import annotations

import calendar
import uuid
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.core.constants import EligibilityReason, LeadTimeClass, OrderStatus
from app.integrations.bamboohr.client import BambooHRClient
from app.integrations.bamboohr.mapper import map_employee
from app.models.detection_config import BirthdayDetectionConfig
from app.models.supplier import Supplier
from app.repositories.supplier_repository import SupplierRepository
from app.services.eligibility_service import compute_eligibility
from app.services.order_sequence_service import next_order_reference
from app.services.order_service import create_or_get_order


def compute_next_birthday_occurrence(birth_month: int, birth_day: int, today: date) -> tuple[date, int]:
    """Returns (occurrence_date, occurrence_year) for the next upcoming
    occurrence of the given month/day on or after ``today``.

    Feb 29 (birth_day=29, birth_month=2) is treated as Mar 1 in a
    non-leap occurrence year — there is no Feb 29 to land the birthday on,
    and Mar 1 (rather than Feb 28) is the more common real-world
    convention for "day after the missing leap day" birthday observance.
    """
    def _occurrence_for_year(year: int) -> date:
        if birth_month == 2 and birth_day == 29 and not calendar.isleap(year):
            return date(year, 3, 1)
        return date(year, birth_month, birth_day)

    candidate = _occurrence_for_year(today.year)
    if candidate < today:
        candidate = _occurrence_for_year(today.year + 1)
    return candidate, candidate.year


def classify_lead_time(days_remaining: int, config: BirthdayDetectionConfig) -> LeadTimeClass:
    if days_remaining <= config.urgent_threshold_days:
        return LeadTimeClass.URGENT
    if days_remaining <= config.short_notice_threshold_days:
        return LeadTimeClass.SHORT_NOTICE
    return LeadTimeClass.NORMAL


def is_within_scan_window(days_remaining: int, config: BirthdayDetectionConfig) -> bool:
    """Window-based (not exact-N-day): includes anything from
    ``window_lookback_days`` in the past through ``window_lookahead_days``
    in the future."""
    return -config.window_lookback_days <= days_remaining <= config.window_lookahead_days


def resolve_supplier_for_office(office_location: str, db: Session) -> Supplier | None:
    return SupplierRepository(db).get_by_office_location(office_location)


def determine_initial_status(
    *,
    lead_time_class: LeadTimeClass,
    days_remaining: int,
    supplier: Supplier | None,
    has_work_email: bool,
) -> tuple[OrderStatus, bool, str | None]:
    """Returns (status, requires_admin_review, hold_reason).

    Missing critical employee data (no work_email) is checked first and
    always wins, regardless of lead time or supplier resolution.
    """
    if not has_work_email:
        return OrderStatus.REQUIRES_ATTENTION, False, "Missing employee email"

    if supplier is None:
        return OrderStatus.REQUIRES_ATTENTION, False, "No supplier resolved for office"

    if days_remaining >= supplier.lead_time_days:
        # DRAFT, not PLANNED (Phase-Next §2): auto-detected orders now go
        # through the same explicit approval workflow as manual ones —
        # nothing is auto-sent to a supplier without a human APPROVE.
        return OrderStatus.DRAFT, lead_time_class != LeadTimeClass.NORMAL, None

    return OrderStatus.ON_HOLD, False, "Supplier lead time exceeds remaining days"


def run_daily_scan(
    db: Session,
    bamboohr_client: BambooHRClient,
    config: BirthdayDetectionConfig,
    *,
    today: date | None = None,
) -> dict:
    run_id = str(uuid.uuid4())
    today = today or datetime.now(UTC).date()

    employees_scanned = 0
    orders_created = 0
    orders_existing = 0
    exceptions = 0
    ineligible_skipped = 0
    errors: list[dict] = []

    for raw_employee in bamboohr_client.list_active_employees():
        employees_scanned += 1
        try:
            employee = map_employee(raw_employee)

            occurrence_date, occurrence_year = compute_next_birthday_occurrence(
                employee["birth_month"], employee["birth_day"], today
            )
            days_remaining = (occurrence_date - today).days

            if not is_within_scan_window(days_remaining, config):
                continue

            # Eligibility gate (plan requirement: never create a cake order
            # for an ineligible employee). Checked before any order is
            # created — an ineligible employee never gets a BirthdayOrder
            # row at all, not one that's created and then held/blocked.
            # `list_active_employees()` already filtered to status=Active,
            # but that alone is insufficient — a real BambooHR tenant can
            # show status=Active before an employee's hire date (confirmed
            # live 2026-08-14), so the hire-date/termination checks below
            # are not redundant with the client-level active filter.
            eligible, reason = compute_eligibility(
                employment_status=employee["employment_status"],
                hire_date=employee.get("hire_date"),
                termination_date=employee.get("termination_date"),
                birth_month=employee["birth_month"],
                birth_day=employee["birth_day"],
                occurrence_date=occurrence_date,
            )
            if not eligible:
                ineligible_skipped += 1
                if reason != EligibilityReason.FUTURE_STARTER:
                    # A future starter is an expected, routine case (not
                    # worth an exception-queue entry); anything else
                    # ineligible this late in the pipeline is unusual
                    # enough to count toward the exceptions total.
                    exceptions += 1
                continue

            lead_time_class = classify_lead_time(days_remaining, config)
            supplier = resolve_supplier_for_office(employee["office_location"], db)
            has_work_email = bool(employee["work_email"])

            status, requires_admin_review, hold_reason = determine_initial_status(
                lead_time_class=lead_time_class,
                days_remaining=days_remaining,
                supplier=supplier,
                has_work_email=has_work_email,
            )

            order_reference = next_order_reference(db, employee["employee_id"], occurrence_year)

            _order, created = create_or_get_order(
                db,
                employee_id=employee["employee_id"],
                employee_number=employee.get("employee_number"),
                employee_name=employee["full_name"],
                employee_email=employee["work_email"],
                order_reference=order_reference,
                birthday_date=occurrence_date,
                birthday_year=occurrence_year,
                office_location=employee["office_location"],
                lead_time_days=days_remaining,
                lead_time_class=lead_time_class.value,
                status=status,
                requires_admin_review=requires_admin_review,
                hold_reason=hold_reason,
                supplier_id=supplier.id if supplier else None,
            )

            if created:
                orders_created += 1
                if status in (OrderStatus.REQUIRES_ATTENTION, OrderStatus.ON_HOLD):
                    exceptions += 1
                elif status == OrderStatus.DRAFT:
                    # Auto-promote DRAFT -> READY_FOR_APPROVAL when every
                    # mandatory fact is already present (rare at detection
                    # time, since address verification is P&C-manual, but
                    # possible for a re-verified employee's next-year
                    # occurrence). Staying DRAFT is not an error.
                    from app.services import order_status_service, readiness_service

                    readiness = readiness_service.check(_order)
                    if readiness.ready:
                        try:
                            order_status_service.submit_for_approval(db, _order, actor_id=None)
                        except order_status_service.ReadinessNotMetError:
                            pass
            else:
                orders_existing += 1

            # Commit per-employee so one employee's failure (below) can be
            # rolled back in isolation without discarding prior employees'
            # already-processed orders in this same run.
            db.commit()

        except Exception as exc:  # noqa: BLE001 - one employee failing must not abort the run
            db.rollback()
            exceptions += 1
            errors.append({"employee_id": getattr(raw_employee, "id", None), "error": str(exc)})

    return {
        "run_id": run_id,
        "employees_scanned": employees_scanned,
        "orders_created": orders_created,
        "orders_existing": orders_existing,
        "exceptions": exceptions,
        "ineligible_skipped": ineligible_skipped,
        "errors": errors,
    }
