"""Dev-only supplier persona provider tests (Phase-Next §5/§6): must be
disabled in production, and the minted token must resolve through the
same SupplierScope path production Entra B2B tokens will use."""

from __future__ import annotations


def test_dev_supplier_login_mints_working_portal_token(api_client, db):
    from app.models.supplier import Supplier
    from app.models.supplier_user import SupplierUser

    supplier = Supplier(name="Dev Auth Supplier", primary_contact_email="devauth@supplier.example.com")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    supplier_user = SupplierUser(supplier_id=supplier.id, email="persona@supplier.example.com", full_name="Persona User")
    db.add(supplier_user)
    db.commit()
    db.refresh(supplier_user)

    login = api_client.post(
        "/api/birthday/internal/dev/supplier-login", json={"supplier_user_id": supplier_user.id},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = api_client.get("/api/birthday/portal/orders", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_dev_supplier_login_unknown_persona_404s(api_client, db):
    resp = api_client.post("/api/birthday/internal/dev/supplier-login", json={"supplier_user_id": 999999})
    assert resp.status_code == 404


def test_dev_supplier_endpoints_disabled_in_production(api_client, db, monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        resp = api_client.post(
            "/api/birthday/internal/dev/supplier-login", json={"supplier_user_id": 1},
        )
        assert resp.status_code == 404
        resp2 = api_client.get("/api/birthday/internal/dev/supplier-users")
        assert resp2.status_code == 404
    finally:
        monkeypatch.delenv("APP_ENV", raising=False)
        get_settings.cache_clear()
