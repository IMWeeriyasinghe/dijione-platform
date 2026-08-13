"""admin-api's client-name enrichment path — protected by the internal
service secret, never a per-user token (CR §48)."""

import os

from tests.conftest import headers_for


def test_clients_lite_requires_internal_token(api_client, db, two_tenant_world):
    resp = api_client.get("/api/talent/internal/clients-lite")
    assert resp.status_code == 401


def test_clients_lite_rejects_a_user_bearer_token(api_client, db, two_tenant_world):
    resp = api_client.get("/api/talent/internal/clients-lite", headers=headers_for(1, role="TA_MEMBER"))
    assert resp.status_code == 401


def test_clients_lite_returns_all_clients(api_client, db, two_tenant_world):
    resp = api_client.get(
        "/api/talent/internal/clients-lite",
        headers={"X-Internal-Token": os.environ["INTERNAL_SERVICE_SECRET"]},
    )
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()}
    assert names == {"ABC Company", "XYZ Company"}
