"""Temporary cross-service guard (Data Ownership Architecture v2 §9):
a client_id named in a module/group client-scope must actually exist in
talent-api. Unknown -> 400; talent-api unreachable -> 503 (fail-safe).

``client_directory.known_client_ids`` makes a real HTTP call, so every test
here patches it.
"""

import httpx
import pytest

from app.services import client_directory
from tests.conftest import ABC_CLIENT_ID, auth_headers

MODULE = "talent-flow"


@pytest.fixture()
def known_clients(monkeypatch):
    def _fake_known() -> set[int]:
        return {ABC_CLIENT_ID}  # only client 1 exists in talent-api

    monkeypatch.setattr(client_directory, "known_client_ids", _fake_known)


def _put_scope(api_client, headers, user_id, client_ids):
    return api_client.put(
        f"/api/platform/admin/users/{user_id}/modules/{MODULE}",
        headers=headers,
        json={
            "role": "TA_MEMBER",
            "enabled": True,
            "client_scope": {"all_clients": False, "client_ids": client_ids},
        },
    )


def test_known_client_id_is_accepted(api_client, two_tenant_world, known_clients):
    headers = auth_headers(api_client, "test-super-admin")
    resp = _put_scope(api_client, headers, two_tenant_world["ta_user"].id, [ABC_CLIENT_ID])
    assert resp.status_code == 200, resp.text


def test_unknown_client_id_is_rejected_400(api_client, two_tenant_world, known_clients):
    headers = auth_headers(api_client, "test-super-admin")
    resp = _put_scope(api_client, headers, two_tenant_world["ta_user"].id, [ABC_CLIENT_ID, 999])
    assert resp.status_code == 400
    assert "999" in resp.text


def test_all_clients_scope_skips_validation(api_client, two_tenant_world, monkeypatch):
    # all_clients=True must not trigger an HTTP call at all.
    def _boom() -> set[int]:
        raise AssertionError("known_client_ids should not be called for all_clients scope")

    monkeypatch.setattr(client_directory, "known_client_ids", _boom)
    headers = auth_headers(api_client, "test-super-admin")
    resp = api_client.put(
        f"/api/platform/admin/users/{two_tenant_world['ta_user'].id}/modules/{MODULE}",
        headers=headers,
        json={"role": "TA_MEMBER", "enabled": True, "client_scope": {"all_clients": True, "client_ids": []}},
    )
    assert resp.status_code == 200, resp.text


def test_talent_api_unreachable_is_503(api_client, two_tenant_world, monkeypatch):
    def _unreachable() -> set[int]:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(client_directory, "known_client_ids", _unreachable)
    headers = auth_headers(api_client, "test-super-admin")
    resp = _put_scope(api_client, headers, two_tenant_world["ta_user"].id, [ABC_CLIENT_ID])
    assert resp.status_code == 503
