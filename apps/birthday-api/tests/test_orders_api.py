"""Phase C route tests: permission gating, manual-create dedup conflict,
dashboard/upcoming/config shapes."""

from datetime import date, timedelta

from tests.conftest import headers_for


def test_list_orders_forbidden_without_module_claim(api_client, db):
    # No birthday module claim at all -> 403 from get_birthday_scope.
    resp = api_client.get("/api/birthday/orders", headers=headers_for(1))
    assert resp.status_code == 403


def test_list_orders_allowed_with_permission(api_client, db):
    resp = api_client.get("/api/birthday/orders", headers=headers_for(2, role="BIRTHDAY_USER"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_create_order_then_duplicate_returns_409(api_client, db):
    payload = {
        "employee_id": "emp-500",
        "employee_name": "Jane Doe",
        "employee_email": "jane@example.com",
        "birthday_date": str(date.today() + timedelta(days=30)),
        "office_location": "Colombo",
    }
    headers = headers_for(3, role="BIRTHDAY_ADMIN")

    resp1 = api_client.post("/api/birthday/orders", json=payload, headers=headers)
    assert resp1.status_code == 201
    order1 = resp1.json()

    resp2 = api_client.post("/api/birthday/orders", json=payload, headers=headers)
    assert resp2.status_code == 409
    body = resp2.json()["detail"]
    assert body["existing_order"]["order_reference"] == order1["order_reference"]

    # Only one row should exist.
    listed = api_client.get("/api/birthday/orders", headers=headers).json()
    assert listed["total"] == 1
    assert len(listed["items"]) == 1


def test_create_order_forbidden_without_create_permission(api_client, db):
    payload = {
        "employee_id": "emp-501",
        "employee_name": "John Roe",
        "employee_email": "john@example.com",
        "birthday_date": str(date.today() + timedelta(days=10)),
        "office_location": "Colombo",
    }
    resp = api_client.post(
        "/api/birthday/orders", json=payload, headers=headers_for(4, role="BIRTHDAY_USER")
    )
    assert resp.status_code == 403


def test_hold_release_cancel_lifecycle(api_client, db):
    headers = headers_for(5, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "emp-600",
        "employee_name": "Amy Lee",
        "employee_email": "amy@example.com",
        "birthday_date": str(date.today() + timedelta(days=20)),
        "office_location": "Colombo",
    }
    created = api_client.post("/api/birthday/orders", json=payload, headers=headers).json()
    order_id = created["id"]
    assert created["status"] == "DRAFT"  # Phase-Next §2: manual orders now start DRAFT, not PLANNED

    held = api_client.post(f"/api/birthday/orders/{order_id}/hold", json={"hold_reason": "check details"}, headers=headers)
    assert held.status_code == 200
    assert held.json()["status"] == "ON_HOLD"

    released = api_client.post(f"/api/birthday/orders/{order_id}/release", json={}, headers=headers)
    assert released.status_code == 200
    assert released.json()["status"] == "PLANNED"

    cancelled = api_client.post(f"/api/birthday/orders/{order_id}/cancel", json={"reason": "cancelled"}, headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"

    detail = api_client.get(f"/api/birthday/orders/{order_id}", headers=headers).json()
    event_types = [e["event_type"] for e in detail["events"]]
    assert event_types.count("STATUS_CHANGE") >= 3


def test_dashboard_endpoint(api_client, db):
    resp = api_client.get("/api/birthday/dashboard", headers=headers_for(6, role="BIRTHDAY_USER"))
    assert resp.status_code == 200
    body = resp.json()
    assert "total_orders" in body
    assert "by_status" in body
    assert "by_lead_time_class" in body


def test_upcoming_endpoint(api_client, db):
    resp = api_client.get("/api/birthday/upcoming", headers=headers_for(7, role="BIRTHDAY_USER"))
    assert resp.status_code == 200
    body = resp.json()
    assert "orders" in body


def test_config_get_and_patch(api_client, db):
    headers = headers_for(8, role="BIRTHDAY_ADMIN")
    resp = api_client.get("/api/birthday/config", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["normal_threshold_days"] == 10

    patched = api_client.patch(
        "/api/birthday/config", json={"normal_threshold_days": 12}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["normal_threshold_days"] == 12


def test_config_forbidden_for_non_admin(api_client, db):
    resp = api_client.get("/api/birthday/config", headers=headers_for(9, role="BIRTHDAY_USER"))
    assert resp.status_code == 403
