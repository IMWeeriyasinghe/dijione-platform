"""Detection-service correctness and idempotency tests (Phase B).

The central proof this file is responsible for: running the daily scan
twice against the same roster must never create duplicate orders — the
DB unique constraint on (employee_id, birthday_year) is the enforcement
point, exercised here end to end through the service layer, not just in
isolation.
"""

import os
from datetime import date

from app.core.constants import LeadTimeClass, OrderStatus
from app.integrations.people_source.mock_adapter import MockEmployeeSource
from app.models.detection_config import BirthdayDetectionConfig
from app.models.supplier import Supplier
from app.models.supplier_location import SupplierLocation
from app.services.detection_service import (
    determine_initial_status,
    is_within_scan_window,
    run_daily_scan,
)
from app.services.order_sequence_service import next_order_reference


def _default_config() -> BirthdayDetectionConfig:
    return BirthdayDetectionConfig(
        normal_threshold_days=10,
        short_notice_threshold_days=5,
        urgent_threshold_days=2,
        window_lookback_days=1,
        window_lookahead_days=14,
        default_quantity=1,
        verify_buffer_days=2,
        acknowledgement_sla_hours=24,
        auto_release_enabled=True,
    )


def _seed_suppliers(db):
    """Suppliers covering the mock roster's office locations. Colombo/Kandy
    get a generous lead time so PLANNED is reachable; Galle gets a tight
    lead time so the ON_HOLD branch is reachable for its late-detection
    employees."""
    generous = Supplier(name="Generous Bakes", lead_time_days=3)
    tight = Supplier(name="Tight Bakes", lead_time_days=10)
    db.add_all([generous, tight])
    db.flush()

    db.add_all(
        [
            SupplierLocation(supplier_id=generous.id, office_location="Colombo"),
            SupplierLocation(supplier_id=generous.id, office_location="Kandy"),
            SupplierLocation(supplier_id=tight.id, office_location="Galle"),
        ]
    )
    db.commit()
    return generous, tight


def test_run_daily_scan_twice_is_idempotent(db):
    _seed_suppliers(db)
    config = _default_config()
    client = MockEmployeeSource()

    first = run_daily_scan(db, client, config)
    assert first["orders_created"] > 0
    assert first["errors"] == []

    second = run_daily_scan(db, client, config)
    assert second["orders_created"] == 0
    assert second["orders_existing"] == first["orders_created"]
    assert second["employees_scanned"] == first["employees_scanned"]


def test_window_boundary_included_and_excluded():
    config = _default_config()
    # window_lookahead_days=14: 13 is inside, 16 is outside.
    assert is_within_scan_window(13, config) is True
    assert is_within_scan_window(16, config) is False
    # Not an exact-N-day check: several distinct values below the boundary
    # must also be included.
    assert is_within_scan_window(0, config) is True
    assert is_within_scan_window(5, config) is True
    assert is_within_scan_window(14, config) is True
    assert is_within_scan_window(15, config) is False
    # Lookback boundary.
    assert is_within_scan_window(-1, config) is True
    assert is_within_scan_window(-2, config) is False


def test_new_joiner_late_detection_pending_verification_when_supplier_can_still_fulfil(db):
    supplier = Supplier(name="Fast Bakes", lead_time_days=1)
    db.add(supplier)
    db.flush()

    status, exception_reason = determine_initial_status(
        lead_time_class=LeadTimeClass.URGENT,
        days_remaining=2,
        supplier=supplier,
        has_work_email=True,
        has_default_cake=False,
    )
    # A resolvable, in-time order lands in PENDING_VERIFICATION regardless
    # of lead-time class — URGENT/SHORT_NOTICE flags the order for review
    # only *after* verification (see address_verification_service), not
    # by keeping it out of the queue.
    assert status == OrderStatus.PENDING_VERIFICATION
    assert exception_reason is None


def test_new_joiner_late_detection_on_hold_when_supplier_cannot_fulfil(db):
    supplier = Supplier(name="Slow Bakes", lead_time_days=10)
    db.add(supplier)
    db.flush()

    status, exception_reason = determine_initial_status(
        lead_time_class=LeadTimeClass.URGENT,
        days_remaining=2,
        supplier=supplier,
        has_work_email=True,
        has_default_cake=False,
    )
    assert status == OrderStatus.ON_HOLD
    assert exception_reason is None


def test_missing_email_requires_attention_regardless_of_supplier(db):
    supplier = Supplier(name="Any Bakes", lead_time_days=1)
    db.add(supplier)
    db.flush()

    status, exception_reason = determine_initial_status(
        lead_time_class=LeadTimeClass.NORMAL,
        days_remaining=10,
        supplier=supplier,
        has_work_email=False,
        has_default_cake=False,
    )
    assert status == OrderStatus.REQUIRES_ATTENTION
    assert exception_reason == "MISSING_EMAIL"


def test_no_resolvable_supplier_requires_attention():
    status, exception_reason = determine_initial_status(
        lead_time_class=LeadTimeClass.NORMAL,
        days_remaining=10,
        supplier=None,
        has_work_email=True,
        has_default_cake=False,
    )
    assert status == OrderStatus.REQUIRES_ATTENTION
    assert exception_reason == "NO_SUPPLIER"


def test_no_default_cake_requires_attention_when_supplier_has_catalogue():
    from app.models.supplier_catalogue_item import SupplierCatalogueItem

    supplier = Supplier(name="Multi Cake Bakes", lead_time_days=1)
    supplier.catalogue_items = [
        SupplierCatalogueItem(name="Chocolate", is_active=True, is_default=False),
        SupplierCatalogueItem(name="Vanilla", is_active=True, is_default=False),
    ]
    status, exception_reason = determine_initial_status(
        lead_time_class=LeadTimeClass.NORMAL,
        days_remaining=10,
        supplier=supplier,
        has_work_email=True,
        has_default_cake=False,
    )
    assert status == OrderStatus.REQUIRES_ATTENTION
    assert exception_reason == "NO_DEFAULT_CAKE"


def test_order_reference_format_and_increment(db):
    year = date.today().year + 1  # avoid collisions with scan-created orders
    ref1 = next_order_reference(db, "1042", year)
    ref2 = next_order_reference(db, "1099", year)
    db.commit()

    assert ref1 == f"BDAY-EMP1042-{year}-00001"
    assert ref2 == f"BDAY-EMP1099-{year}-00002"


def test_run_daily_scan_end_to_end_produces_expected_statuses(db):
    _seed_suppliers(db)
    config = _default_config()
    client = MockEmployeeSource()

    summary = run_daily_scan(db, client, config)

    assert summary["employees_scanned"] == len(client.list_active_employees())
    assert summary["orders_created"] > 0
    # Missing-email employee (bhr-1005) and no-supplier employee (bhr-1010,
    # office "Unassigned Office") are both within window and both land in
    # REQUIRES_ATTENTION, so exceptions must be > 0.
    assert summary["exceptions"] > 0


def test_scan_run_endpoint_requires_internal_token(api_client, db):
    resp = api_client.post("/api/birthday/internal/run-daily-scan")
    assert resp.status_code == 401


def test_scan_run_endpoint_succeeds_with_internal_token(api_client, db):
    _seed_suppliers(db)
    resp = api_client.post(
        "/api/birthday/internal/run-daily-scan",
        headers={"X-Internal-Token": os.environ["INTERNAL_SERVICE_SECRET"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body
    assert body["employees_scanned"] > 0


def test_scan_run_endpoint_rejects_wrong_token(api_client, db):
    resp = api_client.post(
        "/api/birthday/internal/run-daily-scan",
        headers={"X-Internal-Token": "wrong-secret"},
    )
    assert resp.status_code == 401


def test_future_starter_never_gets_an_order(db):
    """Eligibility gate (plan requirement #6/#10): a future starter
    (bhr-1012 in the mock roster — status Active, hire date after this
    occurrence's birthday) must never get a BirthdayOrder row created for
    them, even though the scan window includes their birthday."""
    _seed_suppliers(db)
    config = _default_config()
    client = MockEmployeeSource()

    summary = run_daily_scan(db, client, config)
    assert summary["ineligible_skipped"] >= 1

    from app.repositories.birthday_order_repository import BirthdayOrderRepository

    repo = BirthdayOrderRepository(db)
    orders_for_future_starter = [o for o in repo.list() if o.employee_id == "bhr-1012"]
    assert orders_for_future_starter == []


def test_7_days_away_birthday_is_within_scan_window_and_creates_order(db):
    """Explicit 7-days-away boundary check requested for the eligibility/
    detection test matrix — distinct from the generic window-boundary unit
    test above, exercised through the full scan pipeline."""
    from app.integrations.people_source.mock_adapter import MockEmployeeSource as _Client
    from app.integrations.people_source.schemas import EmployeeRecord

    class _SevenDayClient(_Client):
        def list_active_employees(self):
            d = date.today()
            import datetime as _dt

            occurrence = d + _dt.timedelta(days=7)
            return [
                EmployeeRecord(
                    id="emp-7day",
                    first_name="Seven",
                    last_name="Day",
                    display_name="Seven Day",
                    work_email="seven.day@example.com",
                    birth_month=occurrence.month,
                    birth_day=occurrence.day,
                    department="Engineering",
                    office_location="Colombo",
                    employment_status="Active",
                    hire_date="2019-01-01",
                )
            ]

    generous, _tight = _seed_suppliers(db)
    config = _default_config()
    summary = run_daily_scan(db, _SevenDayClient(), config)
    assert summary["orders_created"] == 1

    from app.repositories.birthday_order_repository import BirthdayOrderRepository

    order = BirthdayOrderRepository(db).get_by_employee_and_year(
        "emp-7day", (date.today() + __import__("datetime").timedelta(days=7)).year
    )
    assert order is not None
    assert order.status in (
        OrderStatus.PENDING_VERIFICATION.value, OrderStatus.ON_HOLD.value,
    )


def test_december_to_january_boundary_scan(db):
    """Dec -> Jan boundary through the full scan pipeline: an employee
    whose birthday is early January must be detected as an upcoming
    occurrence next year when "today" is late December, not skipped as
    already past."""
    from app.integrations.people_source.mock_adapter import MockEmployeeSource as _Client
    from app.integrations.people_source.schemas import EmployeeRecord

    class _YearBoundaryClient(_Client):
        def list_active_employees(self):
            return [
                EmployeeRecord(
                    id="emp-newyear",
                    first_name="New",
                    last_name="Year",
                    display_name="New Year",
                    work_email="new.year@example.com",
                    birth_month=1,
                    birth_day=3,
                    department="Engineering",
                    office_location="Colombo",
                    employment_status="Active",
                    hire_date="2019-01-01",
                )
            ]

    _seed_suppliers(db)
    config = _default_config()
    today = date(2025, 12, 28)
    summary = run_daily_scan(db, _YearBoundaryClient(), config, today=today)
    assert summary["orders_created"] == 1

    from app.repositories.birthday_order_repository import BirthdayOrderRepository

    order = BirthdayOrderRepository(db).get_by_employee_and_year("emp-newyear", 2026)
    assert order is not None
    assert order.birthday_date == date(2026, 1, 3)


def test_duplicate_scan_retry_does_not_create_second_order_for_same_employee(db):
    """Duplicate-retry protection through the full scan pipeline (distinct
    from test_run_daily_scan_twice_is_idempotent's whole-roster check) —
    running the scan three times back to back must still leave exactly one
    order for a single fixed employee."""
    _seed_suppliers(db)
    config = _default_config()
    client = MockEmployeeSource()

    run_daily_scan(db, client, config)
    run_daily_scan(db, client, config)
    third = run_daily_scan(db, client, config)
    assert third["orders_created"] == 0

    from app.repositories.birthday_order_repository import BirthdayOrderRepository

    repo = BirthdayOrderRepository(db)
    # bhr-1001 is a plain eligible employee in the mock roster.
    orders = [o for o in repo.list() if o.employee_id == "bhr-1001"]
    assert len(orders) == 1


def test_run_daily_scan_defers_safely_when_source_is_unavailable(db):
    """Architecture Completion Plan Wave E: people-api unreachable ->
    run_daily_scan defers instead of raising mid-run. No BirthdayOrder is
    touched; the ScanRun is recorded as DEFERRED_SOURCE_UNAVAILABLE, not
    left dangling with no finished_at."""
    from app.integrations.people_source.client import EmployeeSourceClient, EmployeeSourceUnavailableError
    from app.models.scan_run import ScanRun

    class _DownClient(EmployeeSourceClient):
        def list_active_employees(self):
            raise EmployeeSourceUnavailableError("people-api unreachable")

        def get_employee(self, employee_id):
            raise EmployeeSourceUnavailableError("people-api unreachable")

    _seed_suppliers(db)
    config = _default_config()

    result = run_daily_scan(db, _DownClient(), config, trigger="SCHEDULED")
    assert result["status"] == "DEFERRED_SOURCE_UNAVAILABLE"
    assert result["employees_scanned"] == 0
    assert result["orders_created"] == 0

    run = db.query(ScanRun).filter_by(run_id=result["run_id"]).one()
    assert run.status == "DEFERRED_SOURCE_UNAVAILABLE"
    assert run.finished_at is not None  # never left dangling
    assert run.employees_scanned == 0

    from app.repositories.birthday_order_repository import BirthdayOrderRepository

    assert BirthdayOrderRepository(db).list() == []  # nothing was touched


def test_scan_catches_up_after_source_recovers_with_no_duplicates(db):
    """A deferred scan followed by a recovered one must produce exactly the
    same result as if the source had never been unavailable — the forward
    occurrence window + (employee_id, birthday_year) idempotency together
    are what "catches up after recovery" means here."""
    from app.integrations.people_source.client import EmployeeSourceClient, EmployeeSourceUnavailableError

    class _DownClient(EmployeeSourceClient):
        def list_active_employees(self):
            raise EmployeeSourceUnavailableError("down")

        def get_employee(self, employee_id):
            raise EmployeeSourceUnavailableError("down")

    _seed_suppliers(db)
    config = _default_config()

    deferred = run_daily_scan(db, _DownClient(), config)
    assert deferred["status"] == "DEFERRED_SOURCE_UNAVAILABLE"

    recovered = run_daily_scan(db, MockEmployeeSource(), config)
    assert recovered["status"] == "COMPLETED"
    assert recovered["orders_created"] > 0

    # a second recovered run must not duplicate anything the first created.
    again = run_daily_scan(db, MockEmployeeSource(), config)
    assert again["orders_created"] == 0
    assert again["orders_existing"] == recovered["orders_created"] + recovered["orders_existing"]
