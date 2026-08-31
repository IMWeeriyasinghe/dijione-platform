"""Semi-automation future-state end-to-end dry run: BambooHR (mock,
standing in for live) -> detection -> eligibility -> the one address
verification checkpoint (which auto-releases a standard order or flags
one for review) -> supplier visibility -> supplier fulfilment ->
automatic completion, plus the exception scenarios the plan calls out by
name. Asserts real supplier email is never sent (MockGraphEmailClient
only) throughout.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core.config import get_settings
from app.integrations.factory import get_email_client
from app.integrations.graph_email.mock_client import MockGraphEmailClient
from app.integrations.people_source.mock_adapter import MockEmployeeSource
from app.integrations.people_source.schemas import EmployeeRecord
from app.models.detection_config import BirthdayDetectionConfig
from app.models.supplier import Supplier
from app.models.supplier_location import SupplierLocation
from app.services.detection_service import run_daily_scan
from tests.conftest import headers_for, supplier_headers_for


def _config():
    return BirthdayDetectionConfig(
        normal_threshold_days=10, short_notice_threshold_days=5, urgent_threshold_days=2,
        window_lookback_days=1, window_lookahead_days=30,
        default_quantity=1, verify_buffer_days=2, acknowledgement_sla_hours=24,
        auto_release_enabled=True,
    )


def _seed_supplier(db, office_location="Colombo", lead_time_days=3):
    supplier = Supplier(name="Dry Run Bakes", primary_contact_email="dryrun@supplier.example.com", lead_time_days=lead_time_days)
    db.add(supplier)
    db.flush()
    db.add(SupplierLocation(supplier_id=supplier.id, office_location=office_location))
    db.commit()
    db.refresh(supplier)
    return supplier


def test_email_sending_mode_is_mock_by_default():
    """Safety control: EMAIL_SENDING_MODE must default to mock so no code
    path can send real supplier email without an explicit, separate
    opt-in from the BambooHR live/mock switch."""
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.email_sending_mode == "mock"
    assert isinstance(get_email_client(), MockGraphEmailClient)


def test_full_automatic_workflow_bamboohr_to_completion(api_client, db):
    """BambooHR -> detection -> eligibility -> defaulting -> the ONE
    human checkpoint (address verification, which auto-releases a
    standard order) -> supplier fulfilment -> automatic completion. No
    submit/approve/send click exists on this path any more."""
    supplier = _seed_supplier(db)

    class _OneEmployeeClient(MockEmployeeSource):
        def list_active_employees(self):
            occurrence = date.today() + timedelta(days=9)
            return [
                EmployeeRecord(
                    id="dryrun-emp-1", employee_number="501", first_name="Dry", last_name="Run",
                    display_name="Dry Run Employee", work_email="dryrun@example.com",
                    birth_month=occurrence.month, birth_day=occurrence.day,
                    department="Engineering", office_location="Colombo",
                    employment_status="Active", hire_date="2019-01-01",
                )
            ]

    summary = run_daily_scan(db, _OneEmployeeClient(), _config())
    assert summary["orders_created"] == 1
    assert summary["errors"] == []

    from app.repositories.birthday_order_repository import BirthdayOrderRepository

    order = BirthdayOrderRepository(db).get_by_employee_and_year(
        "dryrun-emp-1", (date.today() + timedelta(days=9)).year
    )
    assert order is not None
    assert order.status == "PENDING_VERIFICATION"
    assert order.employee_number == "501"
    assert order.verify_by is not None  # SLA anchor computed at detection

    admin = headers_for(200, role="BIRTHDAY_ADMIN")

    # The ONE human checkpoint: mark the address VERIFIED. Everything
    # else (supplier, delivery date, quantity) was already defaulted by
    # detection, so this auto-releases the order to the supplier.
    verified = api_client.post(f"/api/birthday/orders/{order.id}/verify", json={}, headers=admin)
    assert verified.status_code == 200
    body = verified.json()
    assert body["auto_released"] is True
    assert body["order"]["status"] == "SENT_TO_SUPPLIER"
    assert body["order"]["released_by"] is None  # a SYSTEM release, not a human approval click

    # Real Graph client must never have been touched.
    assert isinstance(get_email_client(), MockGraphEmailClient)

    # Supplier accepts (merged acknowledge+confirm) and fulfils.
    supplier_hdrs = supplier_headers_for(db, supplier)
    accept = api_client.post(f"/api/birthday/portal/orders/{order.id}/accept", headers=supplier_hdrs)
    assert accept.json()["status"] == "CONFIRMED"

    api_client.patch(
        f"/api/birthday/portal/orders/{order.id}/status", json={"status": "PREPARING"}, headers=supplier_hdrs,
    )
    api_client.patch(
        f"/api/birthday/portal/orders/{order.id}/status", json={"status": "OUT_FOR_DELIVERY"}, headers=supplier_hdrs,
    )
    delivered = api_client.patch(
        f"/api/birthday/portal/orders/{order.id}/status", json={"status": "DELIVERED"}, headers=supplier_hdrs,
    )
    # DELIVERED auto-completes immediately — no internal action needed.
    assert delivered.json()["status"] == "COMPLETED"

    detail = api_client.get(f"/api/birthday/orders/{order.id}", headers=admin).json()
    event_types = [e["event_type"] for e in detail["events"]]
    assert "DETECTED" in event_types
    assert "AUTO_RELEASED" in event_types
    assert detail["delivered_at"] is not None
    assert detail["completed_at"] is not None


def test_ad_hoc_workflow_internal_user_creates_order(api_client, db):
    """Internal user -> create order -> fulfilment info -> verify (auto
    release) -> supplier portal."""
    supplier = _seed_supplier(db, office_location="Kandy")
    admin = headers_for(210, role="BIRTHDAY_ADMIN")

    payload = {
        "employee_id": "adhoc-emp-1",
        "employee_number": "601",
        "employee_name": "Ad Hoc Employee",
        "employee_email": "adhoc@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)),
        "office_location": "Kandy",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=admin).json()
    order_id = created["id"]
    assert created["status"] == "PENDING_VERIFICATION"

    api_client.patch(
        f"/api/birthday/orders/{order_id}",
        json={"supplier_id": supplier.id, "delivery_date": str(date.today() + timedelta(days=18))},
        headers=admin,
    )
    verified = api_client.post(f"/api/birthday/orders/{order_id}/verify", json={}, headers=admin)
    assert verified.status_code == 200
    assert verified.json()["order"]["status"] == "SENT_TO_SUPPLIER"

    supplier_hdrs = supplier_headers_for(db, supplier)
    listed = api_client.get("/api/birthday/portal/orders", headers=supplier_hdrs).json()
    assert listed["total"] == 1
    assert listed["items"][0]["order_reference"] == created["order_reference"]


def test_exception_future_starter_never_gets_an_order(db):
    supplier = _seed_supplier(db)
    _ = supplier

    class _FutureStarterClient(MockEmployeeSource):
        def list_active_employees(self):
            occurrence = date.today() + timedelta(days=5)
            return [
                EmployeeRecord(
                    id="exc-future-starter", employee_number="701", first_name="Future", last_name="Starter",
                    display_name="Future Starter", work_email="future@example.com",
                    birth_month=occurrence.month, birth_day=occurrence.day,
                    department="Engineering", office_location="Colombo",
                    employment_status="Active", hire_date=(date.today() + timedelta(days=30)).isoformat(),
                )
            ]

    summary = run_daily_scan(db, _FutureStarterClient(), _config())
    assert summary["orders_created"] == 0


def test_exception_inactive_and_terminated_never_get_orders(db):
    _seed_supplier(db)

    class _InactiveClient(MockEmployeeSource):
        def list_active_employees(self):
            return []  # EmployeeSourceClient contract: inactive/terminated employees are never returned here

    summary = run_daily_scan(db, _InactiveClient(), _config())
    assert summary["orders_created"] == 0


def test_exception_duplicate_order_is_idempotent(db):
    _seed_supplier(db)

    class _RepeatClient(MockEmployeeSource):
        def list_active_employees(self):
            occurrence = date.today() + timedelta(days=9)
            return [
                EmployeeRecord(
                    id="exc-dup", employee_number="702", first_name="Dup", last_name="Licate",
                    display_name="Dup Licate", work_email="dup@example.com",
                    birth_month=occurrence.month, birth_day=occurrence.day,
                    department="Engineering", office_location="Colombo",
                    employment_status="Active", hire_date="2019-01-01",
                )
            ]

    client = _RepeatClient()
    first = run_daily_scan(db, client, _config())
    second = run_daily_scan(db, client, _config())
    assert first["orders_created"] == 1
    assert second["orders_created"] == 0
    assert second["orders_existing"] == 1

    from app.repositories.birthday_order_repository import BirthdayOrderRepository

    order = BirthdayOrderRepository(db).get_by_employee_and_year(
        "exc-dup", (date.today() + timedelta(days=9)).year
    )
    assert order.quantity == 1


def test_detection_falls_back_to_island_wide_default_supplier(db):
    """When no SupplierLocation matches the team member's office, detection
    uses the single ACTIVE supplier flagged is_default instead of dropping
    the order into REQUIRES_ATTENTION."""
    default_supplier = Supplier(
        name="Island Wide Bakes", primary_contact_email="iw@supplier.example.com",
        lead_time_days=3, is_default=True,
    )
    db.add(default_supplier)
    db.commit()
    db.refresh(default_supplier)

    class _NoLocationClient(MockEmployeeSource):
        def list_active_employees(self):
            occurrence = date.today() + timedelta(days=9)
            return [
                EmployeeRecord(
                    id="island-emp", employee_number="790", first_name="Is", last_name="Land",
                    display_name="Is Land", work_email="island@example.com",
                    birth_month=occurrence.month, birth_day=occurrence.day,
                    department="Engineering", office_location="Anuradhapura",  # no SupplierLocation
                    employment_status="Active", hire_date="2019-01-01",
                )
            ]

    summary = run_daily_scan(db, _NoLocationClient(), _config())
    assert summary["orders_created"] == 1

    from app.repositories.birthday_order_repository import BirthdayOrderRepository

    order = BirthdayOrderRepository(db).get_by_employee_and_year(
        "island-emp", (date.today() + timedelta(days=9)).year
    )
    assert order.supplier_id == default_supplier.id
    assert order.status == "PENDING_VERIFICATION"  # not REQUIRES_ATTENTION — a supplier was resolved


def test_exception_missing_supplier_requires_attention(db):
    class _NoSupplierRouteClient(MockEmployeeSource):
        def list_active_employees(self):
            occurrence = date.today() + timedelta(days=9)
            return [
                EmployeeRecord(
                    id="exc-no-supplier", employee_number="703", first_name="No", last_name="Supplier",
                    display_name="No Supplier", work_email="nosupplier@example.com",
                    birth_month=occurrence.month, birth_day=occurrence.day,
                    department="Engineering", office_location="Nowhere",  # no SupplierLocation seeded
                    employment_status="Active", hire_date="2019-01-01",
                )
            ]

    summary = run_daily_scan(db, _NoSupplierRouteClient(), _config())
    assert summary["orders_created"] == 1
    assert summary["exceptions"] == 1

    from app.repositories.birthday_order_repository import BirthdayOrderRepository

    order = BirthdayOrderRepository(db).get_by_employee_and_year(
        "exc-no-supplier", (date.today() + timedelta(days=9)).year
    )
    assert order.status == "REQUIRES_ATTENTION"
    assert order.exception_reason == "NO_SUPPLIER"


def test_exception_missing_fulfilment_info_blocks_verify_release(api_client, db):
    admin = headers_for(220, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "exc-missing-info",
        "employee_name": "Missing Info",
        "employee_email": "missinginfo@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=admin).json()
    resp = api_client.post(f"/api/birthday/orders/{created['id']}/verify", json={}, headers=admin)
    assert resp.status_code == 200
    body = resp.json()
    # Can't auto-release without a supplier — verifying routes it to the
    # exception queue instead of erroring or silently staying put.
    assert body["auto_released"] is False
    assert body["order"]["status"] == "REQUIRES_ATTENTION"


def test_exception_cancelled_path(api_client, db):
    supplier = _seed_supplier(db, office_location="Galle")
    admin = headers_for(230, role="BIRTHDAY_ADMIN")

    payload = {
        "employee_id": "exc-reject-cancel",
        "employee_name": "Reject Cancel",
        "employee_email": "rc@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)),
        "office_location": "Galle",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=admin).json()
    order_id = created["id"]
    api_client.patch(
        f"/api/birthday/orders/{order_id}",
        json={"supplier_id": supplier.id, "delivery_date": str(date.today() + timedelta(days=18))},
        headers=admin,
    )

    cancelled = api_client.post(f"/api/birthday/orders/{order_id}/cancel", json={"reason": "no longer needed"}, headers=admin)
    assert cancelled.json()["status"] == "CANCELLED"


def test_detection_time_exception_recovers_via_verify_once_fixed(api_client, db):
    """A REQUIRES_ATTENTION order from detection (e.g. no supplier
    resolved) is not stuck: once an admin fixes the missing fact
    (assigns a supplier), the same /verify checkpoint that handles the
    normal path also recovers this order — no separate "re-approve"
    step exists any more."""
    admin = headers_for(250, role="BIRTHDAY_ADMIN")

    class _NoSupplierRouteClient(MockEmployeeSource):
        def list_active_employees(self):
            occurrence = date.today() + timedelta(days=9)
            return [
                EmployeeRecord(
                    id="ra-bypass", employee_number="750", first_name="RA", last_name="Bypass",
                    display_name="RA Bypass", work_email="rabypass@example.com",
                    birth_month=occurrence.month, birth_day=occurrence.day,
                    department="Engineering", office_location="Nowhere",
                    employment_status="Active", hire_date="2019-01-01",
                )
            ]

    run_daily_scan(db, _NoSupplierRouteClient(), _config())
    from app.repositories.birthday_order_repository import BirthdayOrderRepository

    order = BirthdayOrderRepository(db).get_by_employee_and_year(
        "ra-bypass", (date.today() + timedelta(days=9)).year
    )
    assert order.status == "REQUIRES_ATTENTION"
    assert order.released_at is None

    supplier = _seed_supplier(db, office_location="Nowhere")
    api_client.patch(
        f"/api/birthday/orders/{order.id}",
        json={"supplier_id": supplier.id, "delivery_date": str(date.today() + timedelta(days=8))},
        headers=admin,
    )

    resp = api_client.post(f"/api/birthday/orders/{order.id}/verify", json={}, headers=admin)
    assert resp.status_code == 200
    body = resp.json()
    assert body["auto_released"] is True
    assert body["order"]["status"] == "SENT_TO_SUPPLIER"


def test_readiness_requires_confirmed_delivery_date(api_client, db):
    """The delivery date is a hard readiness gate. It now defaults to the
    birthday at creation, so this test explicitly clears it to prove the
    gate still fires when it is genuinely absent."""
    supplier = _seed_supplier(db, office_location="Matara")
    admin = headers_for(251, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "needs-delivery-date",
        "employee_name": "Needs Date",
        "employee_email": "needsdate@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)),
        "office_location": "Matara",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=admin).json()
    order_id = created["id"]
    api_client.patch(f"/api/birthday/orders/{order_id}", json={"supplier_id": supplier.id}, headers=admin)

    # Explicitly clear the auto-defaulted delivery date.
    from app.models.birthday_order import BirthdayOrder

    db.get(BirthdayOrder, order_id).delivery_date = None
    db.commit()

    readiness = api_client.get(f"/api/birthday/orders/{order_id}/readiness", headers=admin).json()
    assert readiness["ready"] is False
    assert "delivery_date_missing" in readiness["missing"]

    api_client.patch(
        f"/api/birthday/orders/{order_id}",
        json={"delivery_date": str(date.today() + timedelta(days=18))},
        headers=admin,
    )
    readiness2 = api_client.get(f"/api/birthday/orders/{order_id}/readiness", headers=admin).json()
    assert readiness2["ready"] is False  # address still NOT_CHECKED
    assert "address_not_verified" in readiness2["missing"]


def test_exception_supplier_unable_to_fulfil(api_client, db):
    supplier = _seed_supplier(db, office_location="Colombo")
    admin = headers_for(240, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "exc-unable",
        "employee_name": "Unable Fulfil",
        "employee_email": "unable@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=admin).json()
    order_id = created["id"]
    api_client.patch(
        f"/api/birthday/orders/{order_id}",
        json={"supplier_id": supplier.id, "delivery_date": str(date.today() + timedelta(days=18))},
        headers=admin,
    )
    verified = api_client.post(f"/api/birthday/orders/{order_id}/verify", json={}, headers=admin)
    assert verified.json()["order"]["status"] == "SENT_TO_SUPPLIER"

    supplier_hdrs = supplier_headers_for(db, supplier)
    # A supplier may decline before accepting — no need to Accept first.
    unable = api_client.patch(
        f"/api/birthday/portal/orders/{order_id}/status",
        json={"status": "UNABLE_TO_FULFIL"},
        headers=supplier_hdrs,
    )
    assert unable.status_code == 200
    assert unable.json()["status"] == "UNABLE_TO_FULFIL"
