"""Supplier & SupplierUser administration tests: internal CRUD, status
lifecycle, inactive-supplier order-assignment block, and the
authorization consequences of deactivating a SupplierUser."""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import headers_for, supplier_headers_for


def _create_supplier(api_client, headers, name="Kapruka LK"):
    resp = api_client.post(
        "/api/birthday/suppliers",
        json={"name": name, "primary_contact_email": "orders@kapruka.example.com", "lead_time_days": 2},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


def test_update_supplier_fields(api_client, db):
    admin = headers_for(300, role="BIRTHDAY_ADMIN")
    supplier = _create_supplier(api_client, admin)

    resp = api_client.patch(
        f"/api/birthday/suppliers/{supplier['id']}",
        json={
            "primary_contact_phone": "+94112345678",
            "working_days": "Mon-Sat",
            "cutoff_time": "15:00",
            "escalation_contact_name": "Ops Manager",
            "escalation_contact_email": "ops@kapruka.example.com",
            "lead_time_days": 4,
        },
        headers=admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["primary_contact_phone"] == "+94112345678"
    assert body["working_days"] == "Mon-Sat"
    assert body["lead_time_days"] == 4


def test_deactivate_and_reactivate_supplier(api_client, db):
    admin = headers_for(301, role="BIRTHDAY_ADMIN")
    supplier = _create_supplier(api_client, admin)
    assert supplier["status"] == "ACTIVE"

    deactivated = api_client.patch(
        f"/api/birthday/suppliers/{supplier['id']}", json={"status": "INACTIVE"}, headers=admin,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "INACTIVE"

    # Still fetchable (never deleted) and visible via the status filter.
    fetched = api_client.get(f"/api/birthday/suppliers/{supplier['id']}", headers=admin)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "INACTIVE"

    listed_inactive = api_client.get(
        "/api/birthday/suppliers", params={"status_filter": "INACTIVE"}, headers=admin,
    ).json()
    assert any(s["id"] == supplier["id"] for s in listed_inactive["items"])

    reactivated = api_client.patch(
        f"/api/birthday/suppliers/{supplier['id']}", json={"status": "ACTIVE"}, headers=admin,
    )
    assert reactivated.json()["status"] == "ACTIVE"


def test_inactive_supplier_cannot_be_assigned_to_new_order(api_client, db):
    admin = headers_for(302, role="BIRTHDAY_ADMIN")
    supplier = _create_supplier(api_client, admin, name="Inactive Bakes")
    api_client.patch(f"/api/birthday/suppliers/{supplier['id']}", json={"status": "INACTIVE"}, headers=admin)

    payload = {
        "employee_id": "supadmin-emp-1",
        "employee_name": "Supplier Admin Test",
        "employee_email": "supadmintest@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=admin).json()

    resp = api_client.patch(
        f"/api/birthday/orders/{created['id']}", json={"supplier_id": supplier["id"]}, headers=admin,
    )
    assert resp.status_code == 409
    assert "inactive" in resp.json()["detail"].lower()


def test_inactive_supplier_never_auto_resolved_by_detection(db):
    from app.models.supplier import Supplier
    from app.models.supplier_location import SupplierLocation
    from app.repositories.supplier_repository import SupplierRepository

    supplier = Supplier(name="Auto Resolve Test", status="INACTIVE")
    db.add(supplier)
    db.flush()
    db.add(SupplierLocation(supplier_id=supplier.id, office_location="Colombo"))
    db.commit()

    resolved = SupplierRepository(db).get_by_office_location("Colombo")
    assert resolved is None


def test_historical_orders_remain_readable_after_supplier_deactivation(api_client, db):
    admin = headers_for(303, role="BIRTHDAY_ADMIN")
    supplier = _create_supplier(api_client, admin, name="Historical Bakes")

    payload = {
        "employee_id": "supadmin-emp-2",
        "employee_name": "Historical Order Employee",
        "employee_email": "historical@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=admin).json()
    api_client.patch(
        f"/api/birthday/orders/{created['id']}", json={"supplier_id": supplier["id"]}, headers=admin,
    )

    api_client.patch(f"/api/birthday/suppliers/{supplier['id']}", json={"status": "INACTIVE"}, headers=admin)

    fetched_order = api_client.get(f"/api/birthday/orders/{created['id']}", headers=admin)
    assert fetched_order.status_code == 200
    assert fetched_order.json()["supplier_id"] == supplier["id"]

    fetched_supplier = api_client.get(f"/api/birthday/suppliers/{supplier['id']}", headers=admin)
    assert fetched_supplier.status_code == 200
    assert fetched_supplier.json()["status"] == "INACTIVE"


# -- Supplier Users --------------------------------------------------------

def test_create_supplier_user(api_client, db):
    admin = headers_for(310, role="BIRTHDAY_ADMIN")
    supplier = _create_supplier(api_client, admin, name="User Mgmt Bakes")

    resp = api_client.post(
        f"/api/birthday/suppliers/{supplier['id']}/users",
        json={"email": "contact@usermgmt.example.com", "full_name": "Contact Person", "role": "SUPPLIER_ADMIN"},
        headers=admin,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "contact@usermgmt.example.com"
    assert body["role"] == "SUPPLIER_ADMIN"
    assert body["status"] == "ACTIVE"
    assert body["entra_object_id"] is None

    listed = api_client.get(f"/api/birthday/suppliers/{supplier['id']}/users", headers=admin).json()
    assert any(u["email"] == "contact@usermgmt.example.com" for u in listed)


def test_edit_supplier_user_email_and_name(api_client, db):
    admin = headers_for(311, role="BIRTHDAY_ADMIN")
    supplier = _create_supplier(api_client, admin, name="Edit User Bakes")
    created = api_client.post(
        f"/api/birthday/suppliers/{supplier['id']}/users",
        json={"email": "old@edituser.example.com", "full_name": "Old Name"},
        headers=admin,
    ).json()

    updated = api_client.patch(
        f"/api/birthday/suppliers/{supplier['id']}/users/{created['id']}",
        json={"email": "new@edituser.example.com", "full_name": "New Name"},
        headers=admin,
    )
    assert updated.status_code == 200
    assert updated.json()["email"] == "new@edituser.example.com"
    assert updated.json()["full_name"] == "New Name"


def test_deactivate_supplier_user(api_client, db):
    admin = headers_for(312, role="BIRTHDAY_ADMIN")
    supplier = _create_supplier(api_client, admin, name="Deactivate User Bakes")
    created = api_client.post(
        f"/api/birthday/suppliers/{supplier['id']}/users",
        json={"email": "deactivate@example.com", "full_name": "Deactivate Me"},
        headers=admin,
    ).json()

    deactivated = api_client.patch(
        f"/api/birthday/suppliers/{supplier['id']}/users/{created['id']}",
        json={"status": "INACTIVE"},
        headers=admin,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "INACTIVE"


def test_inactive_supplier_user_rejected_by_supplier_portal_auth(api_client, db):
    from app.models.supplier import Supplier

    supplier = Supplier(name="Inactive User Portal Bakes", primary_contact_email="iup@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    inactive_headers = supplier_headers_for(db, supplier, status="INACTIVE")
    resp = api_client.get("/api/birthday/portal/orders", headers=inactive_headers)
    assert resp.status_code == 403


def test_deactivated_supplier_user_disappears_from_dev_persona_list_and_login(api_client, db):
    from app.models.supplier import Supplier
    from app.models.supplier_user import SupplierUser

    supplier = Supplier(name="Dev Persona Bakes", primary_contact_email="dp@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    user = SupplierUser(supplier_id=supplier.id, email="devpersona@example.com", full_name="Dev Persona")
    db.add(user)
    db.commit()
    db.refresh(user)

    personas = api_client.get("/api/birthday/internal/dev/supplier-users").json()
    assert any(p["supplier_user_id"] == user.id for p in personas)

    user.status = "INACTIVE"
    db.commit()

    personas_after = api_client.get("/api/birthday/internal/dev/supplier-users").json()
    assert not any(p["supplier_user_id"] == user.id for p in personas_after)

    login_resp = api_client.post(
        "/api/birthday/internal/dev/supplier-login", json={"supplier_user_id": user.id},
    )
    assert login_resp.status_code == 403


def test_newly_created_supplier_user_immediately_available_as_dev_persona(api_client, db):
    admin = headers_for(313, role="BIRTHDAY_ADMIN")
    supplier = _create_supplier(api_client, admin, name="Immediate Persona Bakes")
    created = api_client.post(
        f"/api/birthday/suppliers/{supplier['id']}/users",
        json={"email": "immediate@example.com", "full_name": "Immediate Persona"},
        headers=admin,
    ).json()

    personas = api_client.get("/api/birthday/internal/dev/supplier-users").json()
    assert any(p["supplier_user_id"] == created["id"] for p in personas)

    login_resp = api_client.post(
        "/api/birthday/internal/dev/supplier-login", json={"supplier_user_id": created["id"]},
    )
    assert login_resp.status_code == 200


def test_supplier_user_email_uniqueness_enforced(api_client, db):
    admin = headers_for(314, role="BIRTHDAY_ADMIN")
    supplier = _create_supplier(api_client, admin, name="Uniqueness Bakes")
    api_client.post(
        f"/api/birthday/suppliers/{supplier['id']}/users",
        json={"email": "dup@example.com", "full_name": "First"},
        headers=admin,
    )
    dup_resp = api_client.post(
        f"/api/birthday/suppliers/{supplier['id']}/users",
        json={"email": "dup@example.com", "full_name": "Second"},
        headers=admin,
    )
    assert dup_resp.status_code == 409


def test_supplier_user_management_requires_manage_permission(api_client, db):
    admin = headers_for(315, role="BIRTHDAY_ADMIN")
    supplier = _create_supplier(api_client, admin, name="Permission Bakes")

    resp = api_client.post(
        f"/api/birthday/suppliers/{supplier['id']}/users",
        json={"email": "noaccess@example.com", "full_name": "No Access"},
        headers=headers_for(316, role="BIRTHDAY_USER"),
    )
    assert resp.status_code == 403


def test_cross_supplier_isolation_still_passes_with_real_supplier_users(api_client, db):
    """Re-confirms Phase-Next §5 isolation continues to hold once
    SupplierScope re-validates against real DB rows (this admin phase's
    change to get_supplier_scope)."""
    from app.models.birthday_order import BirthdayOrder
    from app.models.supplier import Supplier

    supplier_a = Supplier(name="Isolation A", primary_contact_email="a@iso.example.com")
    supplier_b = Supplier(name="Isolation B", primary_contact_email="b@iso.example.com")
    db.add_all([supplier_a, supplier_b])
    db.commit()
    db.refresh(supplier_a)
    db.refresh(supplier_b)

    order_b = BirthdayOrder(
        order_reference="BDAY-EMPisob-2026-00001",
        employee_id="emp-iso-b",
        employee_name="Isolation B Employee",
        employee_email="isob@example.com",
        birthday_date=date.today() + timedelta(days=10),
        birthday_year=(date.today() + timedelta(days=10)).year,
        office_location="Colombo",
        status="SENT_TO_SUPPLIER",
        supplier_id=supplier_b.id,
        address_verification_status="VERIFIED",
    )
    db.add(order_b)
    db.commit()
    db.refresh(order_b)

    headers_a = supplier_headers_for(db, supplier_a)
    resp = api_client.get(f"/api/birthday/portal/orders/{order_b.id}", headers=headers_a)
    assert resp.status_code == 404
