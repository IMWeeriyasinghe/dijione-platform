"""Idempotent BambooHR-driven birthday detection: occurrence computation,
lead-time classification, scan-window filtering, supplier resolution, and
initial-status determination (CR §5/§10/§12).
"""

from __future__ import annotations

import calendar
import json
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.constants import EligibilityReason, ExceptionReason, LeadTimeClass, OrderStatus, ScanRunStatus
from app.integrations.people_source.client import EmployeeSourceClient, EmployeeSourceUnavailableError
from app.integrations.people_source.mapper import map_employee
from app.models.detection_config import BirthdayDetectionConfig
from app.models.scan_run import ScanRun
from app.models.supplier import Supplier
from app.models.supplier_catalogue_item import SupplierCatalogueItem
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
    """Deterministic supplier resolution, in priority order (§5/§6):

    1. exactly one ACTIVE supplier exists            -> that supplier
    2. an office-location rule matches               -> the mapped supplier
    3. one ACTIVE supplier is flagged is_default     -> that supplier
    4. otherwise                                     -> None (operator picks)

    Nothing hardcodes an id or assumes a single supplier forever — step 1
    simply stops making the operator choose when there is no choice.
    """
    repo = SupplierRepository(db)
    return (
        repo.get_sole_active_supplier()
        or repo.get_by_office_location(office_location)
        or repo.get_default()
    )


def resolve_default_catalogue_item(supplier: Supplier | None, db: Session) -> SupplierCatalogueItem | None:
    """The supplier's default cake (plan §31/§L) — auto-applied to every
    new order for that supplier. A supplier with no catalogue items is
    fine (no exception — "Cake" alone is a valid product); a supplier
    with catalogue items but none flagged default, or more than one, is
    ambiguous and raises NO_DEFAULT_CAKE unless exactly one item exists
    (in which case that lone item is the obvious default)."""
    if supplier is None:
        return None
    items = [item for item in supplier.catalogue_items if item.is_active]
    if not items:
        return None
    defaults = [item for item in items if item.is_default]
    if len(defaults) == 1:
        return defaults[0]
    if len(items) == 1:
        return items[0]
    return None  # ambiguous -> NO_DEFAULT_CAKE exception


def determine_initial_status(
    *,
    lead_time_class: LeadTimeClass,
    days_remaining: int,
    supplier: Supplier | None,
    has_work_email: bool,
    has_default_cake: bool,
) -> tuple[OrderStatus, str | None]:
    """Returns (status, exception_reason).

    Missing critical employee data (no work_email) is checked first and
    always wins, regardless of lead time or supplier resolution. A
    standard, resolvable order lands in PENDING_VERIFICATION — the one
    routine human checkpoint (plan §F) — never in an auto-approved state;
    there is no separate approval status any more (decision A).
    """
    if not has_work_email:
        return OrderStatus.REQUIRES_ATTENTION, ExceptionReason.MISSING_EMAIL.value

    if supplier is None:
        return OrderStatus.REQUIRES_ATTENTION, ExceptionReason.NO_SUPPLIER.value

    if not has_default_cake and supplier.catalogue_items:
        return OrderStatus.REQUIRES_ATTENTION, ExceptionReason.NO_DEFAULT_CAKE.value

    if days_remaining >= supplier.lead_time_days:
        return OrderStatus.PENDING_VERIFICATION, None

    return OrderStatus.ON_HOLD, None


def run_daily_scan(
    db: Session,
    employee_client: EmployeeSourceClient,
    config: BirthdayDetectionConfig,
    *,
    today: date | None = None,
    trigger: str = "MANUAL",
) -> dict:
    run_id = str(uuid.uuid4())
    today = today or datetime.now(UTC).date()
    started_at = datetime.now(UTC)

    scan_run = ScanRun(run_id=run_id, trigger=trigger, started_at=started_at)
    db.add(scan_run)
    db.commit()

    try:
        active_employees = employee_client.list_active_employees()
    except EmployeeSourceUnavailableError:
        # people-api is unreachable: defer, touch NOTHING. No invalid/
        # incomplete orders are created; in-flight BirthdayOrders keep
        # working from their stored detection-time snapshots (this
        # function never reads them); the next scan recomputes each
        # employee's *next* occurrence from "today" and — as long as
        # recovery happens within the configured scan-window lookahead —
        # naturally catches up with no duplicates (idempotent on
        # (employee_id, birthday_year)).
        scan_run.status = ScanRunStatus.DEFERRED_SOURCE_UNAVAILABLE.value
        scan_run.finished_at = datetime.now(UTC)
        db.commit()
        return {
            "run_id": run_id,
            "status": ScanRunStatus.DEFERRED_SOURCE_UNAVAILABLE.value,
            "employees_scanned": 0,
            "orders_created": 0,
            "orders_existing": 0,
            "exceptions": 0,
            "ineligible_skipped": 0,
            "errors": [],
        }

    employees_scanned = 0
    orders_created = 0
    orders_existing = 0
    exceptions = 0
    ineligible_skipped = 0
    errors: list[dict] = []

    for raw_employee in active_employees:
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
            default_catalogue_item = resolve_default_catalogue_item(supplier, db)

            status, exception_reason = determine_initial_status(
                lead_time_class=lead_time_class,
                days_remaining=days_remaining,
                supplier=supplier,
                has_work_email=has_work_email,
                has_default_cake=default_catalogue_item is not None,
            )
            requires_admin_review = status == OrderStatus.PENDING_VERIFICATION and lead_time_class != LeadTimeClass.NORMAL
            hold_reason = "Supplier lead time exceeds remaining days" if status == OrderStatus.ON_HOLD else None

            # SLA anchor (plan §J): when this order must be verified by, so
            # the "verification overdue" queue/dashboard card has something
            # to sort and alert on.
            lead_days = supplier.lead_time_days if supplier else 0
            verify_by = occurrence_date - timedelta(days=lead_days + config.verify_buffer_days)

            # Business-facing Team Member ID (BambooHR employeeNumber), NOT
            # the internal record id — see order_sequence_service docstring.
            team_member_id = employee.get("employee_number") or employee["employee_id"]
            order_reference = next_order_reference(db, team_member_id, occurrence_year)

            _order, created = create_or_get_order(
                db,
                employee_id=employee["employee_id"],
                employee_number=employee.get("employee_number"),
                employee_name=employee["full_name"],
                employee_email=employee["work_email"],
                order_reference=order_reference,
                birthday_date=occurrence_date,
                birthday_year=occurrence_year,
                # Default delivery date = the birthday occurrence (§8) —
                # editable later in Fulfilment Assignment.
                delivery_date=occurrence_date,
                office_location=employee["office_location"],
                lead_time_days=days_remaining,
                lead_time_class=lead_time_class.value,
                status=status,
                requires_admin_review=requires_admin_review,
                hold_reason=hold_reason,
                supplier_id=supplier.id if supplier else None,
                catalogue_item_id=default_catalogue_item.id if default_catalogue_item else None,
                verify_by=verify_by,
                exception_reason=exception_reason,
                delivery_address_line1=employee.get("address_line1"),
                delivery_address_line2=employee.get("address_line2"),
                delivery_city=employee.get("city"),
                delivery_state_province=employee.get("state_province"),
                delivery_postal_code=employee.get("postal_code"),
                delivery_country=employee.get("country"),
            )

            if created:
                orders_created += 1
                if status in (OrderStatus.REQUIRES_ATTENTION, OrderStatus.ON_HOLD):
                    exceptions += 1
                # No auto-promotion step here any more: a freshly-detected
                # order's address is always NOT_CHECKED, so there is never
                # anything to promote at detection time. Auto-release
                # happens later, exactly once, the moment a human marks
                # the address VERIFIED — see address_verification_service.
                # verify_and_release. (The old auto-promote-at-scan-time
                # code was dead for this exact reason and has been removed.)
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

    scan_run.finished_at = datetime.now(UTC)
    scan_run.status = ScanRunStatus.COMPLETED.value
    scan_run.employees_scanned = employees_scanned
    scan_run.orders_created = orders_created
    scan_run.orders_existing = orders_existing
    scan_run.exceptions = exceptions
    scan_run.ineligible_skipped = ineligible_skipped
    scan_run.errors_json = json.dumps(errors)
    db.commit()

    return {
        "run_id": run_id,
        "status": ScanRunStatus.COMPLETED.value,
        "employees_scanned": employees_scanned,
        "orders_created": orders_created,
        "orders_existing": orders_existing,
        "exceptions": exceptions,
        "ineligible_skipped": ineligible_skipped,
        "errors": errors,
    }
