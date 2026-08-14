"""Phase D supplier management route tests: CRUD + permission gating."""

from tests.conftest import headers_for


def _create_supplier(api_client, headers, name="Acme Cakes"):
    payload = {
        "name": name,
        "primary_contact_email": "orders@acmecakes.example.com",
        "lead_time_days": 3,
    }
    resp = api_client.post("/api/birthday/suppliers", json=payload, headers=headers)
    assert resp.status_code == 201
    return resp.json()


def test_list_suppliers_forbidden_without_permission(api_client, db):
    resp = api_client.get("/api/birthday/suppliers", headers=headers_for(20))
    assert resp.status_code == 403


def test_create_supplier_forbidden_without_manage_permission(api_client, db):
    resp = api_client.post(
        "/api/birthday/suppliers",
        json={"name": "Acme Cakes"},
        headers=headers_for(21, role="BIRTHDAY_USER"),
    )
    assert resp.status_code == 403


def test_create_and_get_supplier(api_client, db):
    headers = headers_for(22, role="BIRTHDAY_ADMIN")
    created = _create_supplier(api_client, headers)
    assert created["name"] == "Acme Cakes"
    assert created["status"] == "ACTIVE"

    fetched = api_client.get(f"/api/birthday/suppliers/{created['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


def test_list_suppliers(api_client, db):
    headers = headers_for(23, role="BIRTHDAY_ADMIN")
    _create_supplier(api_client, headers, name="Cake Co")
    resp = api_client.get("/api/birthday/suppliers", headers=headers_for(24, role="BIRTHDAY_USER"))
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body
    assert any(s["name"] == "Cake Co" for s in body["items"])


def test_update_supplier(api_client, db):
    headers = headers_for(25, role="BIRTHDAY_ADMIN")
    created = _create_supplier(api_client, headers)
    resp = api_client.patch(
        f"/api/birthday/suppliers/{created['id']}", json={"lead_time_days": 5}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["lead_time_days"] == 5


def test_update_supplier_forbidden_for_read_only_role(api_client, db):
    admin_headers = headers_for(26, role="BIRTHDAY_ADMIN")
    created = _create_supplier(api_client, admin_headers)
    resp = api_client.patch(
        f"/api/birthday/suppliers/{created['id']}",
        json={"lead_time_days": 9},
        headers=headers_for(27, role="BIRTHDAY_USER"),
    )
    assert resp.status_code == 403


def test_add_and_list_location(api_client, db):
    headers = headers_for(28, role="BIRTHDAY_ADMIN")
    created = _create_supplier(api_client, headers)
    add_resp = api_client.post(
        f"/api/birthday/suppliers/{created['id']}/locations",
        json={"office_location": "Colombo"},
        headers=headers,
    )
    assert add_resp.status_code == 201
    assert add_resp.json()["office_location"] == "Colombo"

    list_resp = api_client.get(
        f"/api/birthday/suppliers/{created['id']}/locations", headers=headers_for(29, role="BIRTHDAY_USER")
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_add_locations_forbidden_without_manage(api_client, db):
    headers = headers_for(30, role="BIRTHDAY_ADMIN")
    created = _create_supplier(api_client, headers)
    resp = api_client.post(
        f"/api/birthday/suppliers/{created['id']}/locations",
        json={"office_location": "Kandy"},
        headers=headers_for(31, role="BIRTHDAY_USER"),
    )
    assert resp.status_code == 403


def test_add_and_update_catalogue_item(api_client, db):
    headers = headers_for(32, role="BIRTHDAY_ADMIN")
    created = _create_supplier(api_client, headers)
    add_resp = api_client.post(
        f"/api/birthday/suppliers/{created['id']}/catalogue",
        json={"name": "Chocolate Cake", "description": "1kg chocolate cake"},
        headers=headers,
    )
    assert add_resp.status_code == 201
    item = add_resp.json()
    assert item["name"] == "Chocolate Cake"
    assert item["is_active"] is True

    update_resp = api_client.patch(
        f"/api/birthday/suppliers/{created['id']}/catalogue/{item['id']}",
        json={"is_active": False},
        headers=headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["is_active"] is False

    list_resp = api_client.get(
        f"/api/birthday/suppliers/{created['id']}/catalogue", headers=headers_for(33, role="BIRTHDAY_USER")
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_supplier_not_found(api_client, db):
    headers = headers_for(34, role="BIRTHDAY_ADMIN")
    resp = api_client.get("/api/birthday/suppliers/999999", headers=headers)
    assert resp.status_code == 404
