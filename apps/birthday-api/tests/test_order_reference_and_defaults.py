"""§1-10 / §16 corrections:

A. Order references embed BambooHR employeeNumber (business Team Member ID),
   never the internal record id.
B. Supplier auto-selection when exactly one ACTIVE supplier exists.
C. Delivery date defaults to the birthday occurrence.
D. Product type is always Cake — no catalogue item required for readiness.
E. backfill_order_references is deterministic, idempotent, uniqueness-safe.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.integrations.bamboohr.mock_client import MockBambooHRClient
from app.integrations.bamboohr.schemas import BambooHREmployee
from app.models.birthday_order import BirthdayOrder
from app.models.detection_config import BirthdayDetectionConfig
from app.models.supplier import Supplier
from app.services.detection_service import resolve_supplier_for_office, run_daily_scan
from tests.conftest import headers_for


def _config() -> BirthdayDetectionConfig:
    return BirthdayDetectionConfig(
        normal_threshold_days=10, short_notice_threshold_days=5, urgent_threshold_days=2,
        window_lookback_days=1, window_lookahead_days=30,
        default_quantity=1, verify_buffer_days=2, acknowledgement_sla_hours=24,
        auto_release_enabled=True,
    )


def _one_employee_client(*, internal_id: str, employee_number: str, days_ahead: int = 9):
    occurrence = date.today() + timedelta(days=days_ahead)

    class _Client(MockBambooHRClient):
        def list_active_employees(self):
            return [
                BambooHREmployee(
                    id=internal_id, employee_number=employee_number,
                    first_name="Ref", last_name="Test", display_name="Ref Test",
                    work_email="ref.test@example.com",
                    birth_month=occurrence.month, birth_day=occurrence.day,
                    department="Engineering", office_location="Colombo",
                    employment_status="Active", hire_date="2019-01-01",
                )
            ]

    return _Client(), occurrence


# --- A. Order reference identity ---------------------------------------------

def test_detection_order_reference_uses_employee_number_not_internal_id(db):
    client, occ = _one_employee_client(internal_id="530", employee_number="396")
    run_daily_scan(db, client, _config())

    order = db.query(BirthdayOrder).filter_by(employee_id="530").one()
    assert "EMP396" in order.order_reference
    assert "EMP530" not in order.order_reference
    assert order.order_reference == f"BDAY-EMP396-{occ.year}-00001"
    # internal id mapping is NOT regressed
    assert order.employee_id == "530"
    assert order.employee_number == "396"


def test_detection_order_reference_second_case(db):
    client, occ = _one_employee_client(internal_id="444", employee_number="313")
    run_daily_scan(db, client, _config())

    order = db.query(BirthdayOrder).filter_by(employee_id="444").one()
    assert "EMP313" in order.order_reference
    assert "EMP444" not in order.order_reference


def test_manual_order_reference_uses_employee_number(api_client, db):
    headers = headers_for(500, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "530",
        "employee_number": "396",
        "employee_name": "Ref Test",
        "employee_email": "ref.test@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=headers).json()
    assert "EMP396" in created["order_reference"]
    assert "EMP530" not in created["order_reference"]


def test_order_reference_falls_back_to_internal_id_when_no_employee_number(db):
    client, occ = _one_employee_client(internal_id="777", employee_number="")
    run_daily_scan(db, client, _config())
    order = db.query(BirthdayOrder).filter_by(employee_id="777").one()
    assert order.order_reference == f"BDAY-EMP777-{occ.year}-00001"


# --- B. Supplier auto-selection -------------------------------------------------

def test_sole_active_supplier_is_auto_resolved(db):
    only = Supplier(name="Only Active", status="ACTIVE")
    db.add(only)
    db.commit()
    db.refresh(only)
    # Office string with no SupplierLocation mapping — still resolves.
    assert resolve_supplier_for_office("Anywhere In Sri Lanka", db).id == only.id


def test_multiple_active_suppliers_without_match_do_not_auto_select(db):
    db.add_all([
        Supplier(name="Active One", status="ACTIVE"),
        Supplier(name="Active Two", status="ACTIVE"),
    ])
    db.commit()
    assert resolve_supplier_for_office("Unmapped Office", db) is None


def test_inactive_supplier_is_never_auto_selected(db):
    db.add(Supplier(name="Inactive Only", status="INACTIVE"))
    db.commit()
    assert resolve_supplier_for_office("Anywhere", db) is None


def test_detection_auto_assigns_sole_active_supplier(db):
    only = Supplier(name="Island Wide", status="ACTIVE", primary_contact_email="iw@s.example.com")
    db.add(only)
    db.commit()
    db.refresh(only)

    client, _ = _one_employee_client(internal_id="800", employee_number="800b")
    run_daily_scan(db, client, _config())
    order = db.query(BirthdayOrder).filter_by(employee_id="800").one()
    assert order.supplier_id == only.id
    assert order.status == "PENDING_VERIFICATION"  # supplier resolved -> not REQUIRES_ATTENTION


def test_manual_create_auto_assigns_sole_active_supplier(api_client, db):
    only = Supplier(name="Sole", status="ACTIVE")
    db.add(only)
    db.commit()
    db.refresh(only)

    headers = headers_for(501, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "810", "employee_number": "810b", "employee_name": "M",
        "employee_email": "m@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)), "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=headers).json()
    assert created["supplier_id"] == only.id


# --- C. Delivery date default ------------------------------------------------

def test_detection_defaults_delivery_date_to_birthday_occurrence(db):
    client, occ = _one_employee_client(internal_id="900", employee_number="900b")
    run_daily_scan(db, client, _config())
    order = db.query(BirthdayOrder).filter_by(employee_id="900").one()
    assert order.delivery_date == occ


def test_manual_create_defaults_delivery_date_to_birthday(api_client, db):
    headers = headers_for(502, role="BIRTHDAY_ADMIN")
    bday = date.today() + timedelta(days=20)
    payload = {
        "employee_id": "910", "employee_number": "910b", "employee_name": "M",
        "employee_email": "m@example.com", "birthday_date": str(bday), "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=headers).json()
    assert created["delivery_date"] == str(bday)


def test_delivery_date_manual_override_is_preserved(api_client, db):
    headers = headers_for(503, role="BIRTHDAY_ADMIN")
    bday = date.today() + timedelta(days=20)
    override = date.today() + timedelta(days=19)  # e.g. birthday on a weekend
    payload = {
        "employee_id": "920", "employee_number": "920b", "employee_name": "M",
        "employee_email": "m@example.com", "birthday_date": str(bday),
        "office_location": "Colombo", "delivery_date": str(override),
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=headers).json()
    assert created["delivery_date"] == str(override)

    patched = api_client.patch(
        f"/api/birthday/orders/{created['id']}",
        json={"delivery_date": str(bday)}, headers=headers,
    ).json()
    assert patched["delivery_date"] == str(bday)


# --- D. Product = Cake / no catalogue item required ------------------------

def test_order_is_ready_without_a_catalogue_item(api_client, db):
    supplier = Supplier(name="Ready Supplier", status="ACTIVE", primary_contact_email="r@s.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    headers = headers_for(504, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "930", "employee_number": "930b", "employee_name": "M",
        "employee_email": "m@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)), "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=headers).json()
    assert created["catalogue_item_id"] is None  # product type is implicitly Cake
    api_client.patch(
        f"/api/birthday/orders/{created['id']}/address-verification",
        json={"status": "VERIFIED"}, headers=headers,
    )
    readiness = api_client.get(
        f"/api/birthday/orders/{created['id']}/readiness", headers=headers
    ).json()
    assert readiness["ready"] is True  # supplier + date auto-set, no catalogue item needed


# --- E. Backfill script determinism / idempotency -------------------------

def _seed_order(db, *, ref, emp_id, emp_number, status="PENDING_VERIFICATION"):
    o = BirthdayOrder(
        order_reference=ref, employee_id=emp_id, employee_number=emp_number,
        employee_name="B", employee_email="b@example.com",
        birthday_date=date(2026, 6, 1), birthday_year=2026, office_location="Colombo",
        status=status,
    )
    db.add(o)
    db.commit()
    return o


def test_backfill_order_references_corrects_only_provable_wrong_rows(db):
    from scripts.backfill_order_references import run

    wrong = _seed_order(db, ref="BDAY-EMP530-2026-00001", emp_id="530", emp_number="396")
    already = _seed_order(db, ref="BDAY-EMP313-2026-00002", emp_id="444", emp_number="313")
    no_number = _seed_order(db, ref="BDAY-EMP999-2026-00003", emp_id="999", emp_number=None)

    summary = run()
    assert summary["corrected"] == 1
    db.expire_all()
    assert db.get(BirthdayOrder, wrong.id).order_reference == "BDAY-EMP396-2026-00001"
    assert db.get(BirthdayOrder, already.id).order_reference == "BDAY-EMP313-2026-00002"
    assert db.get(BirthdayOrder, no_number.id).order_reference == "BDAY-EMP999-2026-00003"

    # Idempotent: a second run changes nothing.
    summary2 = run()
    assert summary2["corrected"] == 0
    assert summary2["already_correct"] >= 1


def test_backfill_skips_on_reference_collision(db):
    from scripts.backfill_order_references import run

    _seed_order(db, ref="BDAY-EMP530-2026-00001", emp_id="530", emp_number="396")
    # The corrected reference is already taken by another order.
    _seed_order(db, ref="BDAY-EMP396-2026-00001", emp_id="396", emp_number="396")

    summary = run()
    assert summary["corrected"] == 0
    assert summary["collision"] == 1
