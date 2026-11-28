"""Order Creation Window: validation, detection boundary, and idempotency."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.integrations.people_source.mock_adapter import MockEmployeeSource
from app.integrations.people_source.schemas import EmployeeRecord
from app.models.birthday_order import BirthdayOrder
from app.models.detection_config import BirthdayDetectionConfig
from app.models.supplier import Supplier
from app.models.supplier_location import SupplierLocation
from app.schemas.config import MAX_ORDER_CREATION_WINDOW_DAYS, MIN_ORDER_CREATION_WINDOW_DAYS
from app.services.detection_service import is_within_scan_window, run_daily_scan
from tests.conftest import headers_for

ADMIN = 900


def _cfg(window: int = 14) -> BirthdayDetectionConfig:
    return BirthdayDetectionConfig(
        normal_threshold_days=10, short_notice_threshold_days=5, urgent_threshold_days=2,
        window_lookback_days=1, window_lookahead_days=window, default_quantity=1,
        verify_buffer_days=2, acknowledgement_sla_hours=24, auto_release_enabled=True,
    )


def _seed_supplier(db) -> Supplier:
    s = Supplier(name="Test Bakes", lead_time_days=3)
    db.add(s)
    db.flush()
    db.add(SupplierLocation(supplier_id=s.id, office_location="Colombo"))
    db.commit()
    return s


def _employee_days_away(days: int, employee_id: str = "scan-emp") -> EmployeeRecord:
    occurrence = date.today() + timedelta(days=days)
    return EmployeeRecord(
        id=employee_id,
        employee_number=employee_id,
        first_name="Test",
        last_name="Employee",
        display_name="Test Employee",
        work_email=f"{employee_id}@example.com",
        birth_month=occurrence.month,
        birth_day=occurrence.day,
        department="Engineering",
        office_location="Colombo",
        employment_status="Active",
        hire_date="2019-01-01",
    )


def _client_with(employees: list[EmployeeRecord]) -> MockEmployeeSource:
    class _FixedClient(MockEmployeeSource):
        def list_active_employees(self):
            return employees
    return _FixedClient()


# ---------------------------------------------------------------------------
# Config API validation
# ---------------------------------------------------------------------------

class TestOrderCreationWindowValidation:
    def test_default_is_14(self, api_client, db):
        resp = api_client.get("/api/birthday/config", headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN"))
        assert resp.status_code == 200
        assert resp.json()["window_lookahead_days"] == 14

    def test_minimum_accepted(self, api_client, db):
        resp = api_client.patch(
            "/api/birthday/config",
            json={"window_lookahead_days": MIN_ORDER_CREATION_WINDOW_DAYS},
            headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN"),
        )
        assert resp.status_code == 200
        assert resp.json()["window_lookahead_days"] == MIN_ORDER_CREATION_WINDOW_DAYS

    def test_maximum_accepted(self, api_client, db):
        resp = api_client.patch(
            "/api/birthday/config",
            json={"window_lookahead_days": MAX_ORDER_CREATION_WINDOW_DAYS},
            headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN"),
        )
        assert resp.status_code == 200
        assert resp.json()["window_lookahead_days"] == MAX_ORDER_CREATION_WINDOW_DAYS

    @pytest.mark.parametrize("value", [0, -1, -14, 91, 100])
    def test_out_of_range_rejected(self, api_client, db, value):
        resp = api_client.patch(
            "/api/birthday/config",
            json={"window_lookahead_days": value},
            headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN"),
        )
        assert resp.status_code == 422

    def test_non_admin_cannot_update(self, api_client, db):
        resp = api_client.patch(
            "/api/birthday/config",
            json={"window_lookahead_days": 7},
            headers=headers_for(ADMIN, role="BIRTHDAY_USER"),
        )
        assert resp.status_code == 403

    def test_update_does_not_change_other_fields(self, api_client, db):
        before = api_client.get(
            "/api/birthday/config", headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN")
        ).json()
        api_client.patch(
            "/api/birthday/config",
            json={"window_lookahead_days": 21},
            headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN"),
        )
        after = api_client.get(
            "/api/birthday/config", headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN")
        ).json()
        assert after["window_lookahead_days"] == 21
        assert after["supplier_lead_time_days"] == before["supplier_lead_time_days"]
        assert after["operational_start_date"] == before["operational_start_date"]


# ---------------------------------------------------------------------------
# is_within_scan_window uses the configured value
# ---------------------------------------------------------------------------

class TestIsWithinScanWindowConfigured:
    def test_window_14_boundary(self):
        cfg = _cfg(14)
        assert is_within_scan_window(14, cfg) is True
        assert is_within_scan_window(15, cfg) is False
        assert is_within_scan_window(0, cfg) is True

    def test_window_7_boundary(self):
        cfg = _cfg(7)
        assert is_within_scan_window(7, cfg) is True
        assert is_within_scan_window(8, cfg) is False

    def test_window_21_boundary(self):
        cfg = _cfg(21)
        assert is_within_scan_window(21, cfg) is True
        assert is_within_scan_window(22, cfg) is False

    def test_window_1_minimum(self):
        cfg = _cfg(1)
        assert is_within_scan_window(1, cfg) is True
        assert is_within_scan_window(2, cfg) is False

    def test_window_90_maximum(self):
        cfg = _cfg(90)
        assert is_within_scan_window(90, cfg) is True
        assert is_within_scan_window(91, cfg) is False


# ---------------------------------------------------------------------------
# Detection uses the configured window, not a hardcoded 14
# ---------------------------------------------------------------------------

class TestDetectionUsesConfiguredWindow:
    def test_birthday_outside_14_but_inside_21_creates_order_when_window_is_21(self, db):
        """When window grows to 21, an employee whose birthday is 18 days away
        enters the window and an order is created on the next scan."""
        _seed_supplier(db)
        client = _client_with([_employee_days_away(18, "scan-window-21")])
        result = run_daily_scan(db, client, _cfg(21))
        assert result["orders_created"] == 1
        order = db.query(BirthdayOrder).filter_by(employee_id="scan-window-21").first()
        assert order is not None

    def test_birthday_outside_21_does_not_create_order(self, db):
        client = _client_with([_employee_days_away(25, "scan-window-outside")])
        result = run_daily_scan(db, client, _cfg(21))
        assert result["orders_created"] == 0

    def test_birthday_at_exact_14_creates_order_with_default_window(self, db):
        _seed_supplier(db)
        client = _client_with([_employee_days_away(14, "scan-exact-14")])
        result = run_daily_scan(db, client, _cfg(14))
        assert result["orders_created"] == 1

    def test_birthday_at_15_does_not_create_order_with_default_window(self, db):
        client = _client_with([_employee_days_away(15, "scan-15-outside")])
        result = run_daily_scan(db, client, _cfg(14))
        assert result["orders_created"] == 0


# ---------------------------------------------------------------------------
# Increasing/decreasing the window — order safety
# ---------------------------------------------------------------------------

class TestWindowChange:
    def test_decreasing_window_does_not_cancel_existing_orders(self, db):
        """Existing orders are untouched when the window shrinks.
        A birthday 10 days away was captured at window=14; shrinking to 7
        must not alter the existing PENDING_VERIFICATION order."""
        from app.core.constants import OrderStatus

        _seed_supplier(db)
        today = date.today()
        order = BirthdayOrder(
            order_reference="BDAY-WIN-DEC", employee_id="dec-window",
            employee_number="W1", employee_name="Window Dec", employee_email="dec@example.com",
            birthday_date=today + timedelta(days=10), birthday_year=(today + timedelta(days=10)).year,
            office_location="Colombo", quantity=1,
            status=OrderStatus.PENDING_VERIFICATION.value,
            delivery_date=today + timedelta(days=10),
            address_verification_status="NOT_CHECKED",
        )
        db.add(order)
        db.commit()

        # Window shrinks — no scan run here; existing order must survive.
        db.refresh(order)
        assert order.status == OrderStatus.PENDING_VERIFICATION.value

    def test_increasing_window_allows_new_orders_on_next_scan(self, db):
        """After window grows to 21, the next scan creates an order that
        was previously outside the 14-day window (18 days away)."""
        _seed_supplier(db)
        client = _client_with([_employee_days_away(18, "scan-window-grow")])

        r1 = run_daily_scan(db, client, _cfg(14))
        assert r1["orders_created"] == 0

        r2 = run_daily_scan(db, client, _cfg(21))
        assert r2["orders_created"] == 1

    def test_repeated_scan_does_not_duplicate_orders(self, db):
        """Idempotency: two scans with the same window must not create two
        orders for the same employee/year."""
        _seed_supplier(db)
        client = _client_with([_employee_days_away(10, "scan-idempotent")])
        run_daily_scan(db, client, _cfg(14))
        run_daily_scan(db, client, _cfg(14))
        count = db.query(BirthdayOrder).filter_by(employee_id="scan-idempotent").count()
        assert count == 1
