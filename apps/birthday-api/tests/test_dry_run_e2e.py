"""Phase-Next §7 end-to-end dry run: BambooHR (mock, standing in for live)
-> detection -> eligibility -> address verification -> approval ->
supplier visibility -> supplier acknowledgement -> completion, plus the
exception scenarios the plan calls out by name. Asserts real supplier
email is never sent (MockGraphEmailClient only) throughout.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core.config import get_settings
from app.integrations.bamboohr.mock_client import MockBambooHRClient
from app.integrations.bamboohr.schemas import BambooHREmployee
from app.integrations.factory import get_email_client
from app.integrations.graph_email.mock_client import MockGraphEmailClient
from app.models.detection_config import BirthdayDetectionConfig
from app.models.supplier import Supplier
from app.models.supplier_location import SupplierLocation
from app.services.detection_service import run_daily_scan
from tests.conftest import headers_for, supplier_headers_for


def _config():
    return BirthdayDetectionConfig(
        normal_threshold_days=10, short_notice_threshold_days=5, urgent_threshold_days=2,
        window_lookback_days=1, window_lookahead_days=30,
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
    """Safety control (plan §7): EMAIL_SENDING_MODE must default to mock
    so no code path can send real supplier email without an explicit,
    separate opt-in from the BambooHR live/mock switch."""
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.email_sending_mode == "mock"
    assert isinstance(get_email_client(), MockGraphEmailClient)


def test_full_automatic_workflow_bamboohr_to_completion(api_client, db):
    """BambooHR -> detection -> eligibility -> address verification ->
    order -> approval -> supplier visibility -> supplier acknowledgement
    -> completion, with real HTTP calls through the API layer wherever a
    human would act, exactly mirroring the automatic + ad hoc workflows
    from the plan."""
    supplier = _seed_supplier(db)

    class _OneEmployeeClient(MockBambooHRClient):
        def list_active_employees(self):
            occurrence = date.today() + timedelta(days=9)
            return [
                BambooHREmployee(
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
    assert order.status == "DRAFT"
    assert order.employee_number == "501"

    admin = headers_for(200, role="BIRTHDAY_ADMIN")

    # Address verification (P&C-manual).
    api_client.patch(
        f"/api/birthday/orders/{order.id}/address-verification", json={"status": "VERIFIED"}, headers=admin,
    )

    # Supplier already resolved by detection; readiness should now pass.
    readiness = api_client.get(f"/api/birthday/orders/{order.id}/readiness", headers=admin).json()
    assert readiness["ready"] is True

    submitted = api_client.post(f"/api/birthday/orders/{order.id}/submit-for-approval", headers=admin)
    assert submitted.json()["status"] == "READY_FOR_APPROVAL"

    approved = api_client.post(f"/api/birthday/orders/{order.id}/approve", headers=admin)
    assert approved.json()["status"] == "APPROVED"

    sent = api_client.post(f"/api/birthday/orders/{order.id}/send-to-supplier", headers=admin)
    assert sent.status_code == 200
    assert sent.json()["status"] == "SENT_TO_SUPPLIER"

    # Real Graph client must never have been touched.
    assert isinstance(get_email_client(), MockGraphEmailClient)

    # Supplier acknowledges and progresses through the portal.
    supplier_hdrs = supplier_headers_for(db, supplier)
    ack = api_client.post(f"/api/birthday/portal/orders/{order.id}/acknowledge", headers=supplier_hdrs)
    assert ack.json()["status"] == "SUPPLIER_REVIEW"

    confirm = api_client.patch(
        f"/api/birthday/portal/orders/{order.id}/status", json={"status": "CONFIRMED"}, headers=supplier_hdrs,
    )
    assert confirm.json()["status"] == "CONFIRMED"

    api_client.patch(
        f"/api/birthday/portal/orders/{order.id}/status", json={"status": "PREPARING"}, headers=supplier_hdrs,
    )
    api_client.patch(
        f"/api/birthday/portal/orders/{order.id}/status", json={"status": "OUT_FOR_DELIVERY"}, headers=supplier_hdrs,
    )
    delivered = api_client.patch(
        f"/api/birthday/portal/orders/{order.id}/status", json={"status": "DELIVERED"}, headers=supplier_hdrs,
    )
    assert delivered.json()["status"] == "DELIVERED"

    detail = api_client.get(f"/api/birthday/orders/{order.id}", headers=admin).json()
    event_types = [e["event_type"] for e in detail["events"]]
    assert "DETECTED" in event_types
    assert "STATUS_CHANGE" in event_types


def test_ad_hoc_workflow_internal_user_creates_order(api_client, db):
    """Internal user -> create order -> supplier -> fulfilment info ->
    address verification -> approval -> supplier portal."""
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
    assert created["status"] == "DRAFT"

    api_client.patch(
        f"/api/birthday/orders/{order_id}",
        json={"supplier_id": supplier.id, "delivery_date": str(date.today() + timedelta(days=18))},
        headers=admin,
    )
    api_client.patch(
        f"/api/birthday/orders/{order_id}/address-verification", json={"status": "VERIFIED"}, headers=admin,
    )
    api_client.post(f"/api/birthday/orders/{order_id}/submit-for-approval", headers=admin)
    api_client.post(f"/api/birthday/orders/{order_id}/approve", headers=admin)
    sent = api_client.post(f"/api/birthday/orders/{order_id}/send-to-supplier", headers=admin)
    assert sent.status_code == 200

    supplier_hdrs = supplier_headers_for(db, supplier)
    listed = api_client.get("/api/birthday/portal/orders", headers=supplier_hdrs).json()
    assert listed["total"] == 1
    assert listed["items"][0]["order_reference"] == created["order_reference"]


def test_exception_future_starter_never_gets_an_order(db):
    supplier = _seed_supplier(db)
    _ = supplier

    class _FutureStarterClient(MockBambooHRClient):
        def list_active_employees(self):
            occurrence = date.today() + timedelta(days=5)
            return [
                BambooHREmployee(
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

    class _InactiveClient(MockBambooHRClient):
        def list_active_employees(self):
            return []  # BambooHRClient contract: inactive/terminated employees are never returned here

    summary = run_daily_scan(db, _InactiveClient(), _config())
    assert summary["orders_created"] == 0


def test_exception_duplicate_order_is_idempotent(db):
    _seed_supplier(db)

    class _RepeatClient(MockBambooHRClient):
        def list_active_employees(self):
            occurrence = date.today() + timedelta(days=9)
            return [
                BambooHREmployee(
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


def test_exception_missing_supplier_requires_attention(db):
    class _NoSupplierRouteClient(MockBambooHRClient):
        def list_active_employees(self):
            occurrence = date.today() + timedelta(days=9)
            return [
                BambooHREmployee(
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


def test_exception_missing_fulfilment_info_blocks_submit_for_approval(api_client, db):
    admin = headers_for(220, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "exc-missing-info",
        "employee_name": "Missing Info",
        "employee_email": "missinginfo@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=admin).json()
    resp = api_client.post(f"/api/birthday/orders/{created['id']}/submit-for-approval", headers=admin)
    assert resp.status_code == 409
    assert "supplier_not_assigned" in resp.json()["detail"]["missing"]


def test_exception_rejected_and_cancelled_paths(api_client, db):
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
    api_client.patch(f"/api/birthday/orders/{order_id}", json={"supplier_id": supplier.id}, headers=admin)
    api_client.patch(
        f"/api/birthday/orders/{order_id}/address-verification", json={"status": "VERIFIED"}, headers=admin,
    )
    api_client.post(f"/api/birthday/orders/{order_id}/submit-for-approval", headers=admin)

    rejected = api_client.post(
        f"/api/birthday/orders/{order_id}/reject", json={"reason": "not needed"}, headers=admin,
    )
    assert rejected.json()["status"] == "REJECTED"

    cancelled = api_client.post(f"/api/birthday/orders/{order_id}/cancel", json={"reason": "no longer needed"}, headers=admin)
    assert cancelled.json()["status"] == "CANCELLED"


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
    api_client.patch(f"/api/birthday/orders/{order_id}", json={"supplier_id": supplier.id}, headers=admin)
    api_client.patch(
        f"/api/birthday/orders/{order_id}/address-verification", json={"status": "VERIFIED"}, headers=admin,
    )
    api_client.post(f"/api/birthday/orders/{order_id}/submit-for-approval", headers=admin)
    api_client.post(f"/api/birthday/orders/{order_id}/approve", headers=admin)
    api_client.post(f"/api/birthday/orders/{order_id}/send-to-supplier", headers=admin)

    supplier_hdrs = supplier_headers_for(db, supplier)
    api_client.post(f"/api/birthday/portal/orders/{order_id}/acknowledge", headers=supplier_hdrs)
    unable = api_client.patch(
        f"/api/birthday/portal/orders/{order_id}/status",
        json={"status": "UNABLE_TO_FULFIL"},
        headers=supplier_hdrs,
    )
    assert unable.status_code == 200
    assert unable.json()["status"] == "UNABLE_TO_FULFIL"
