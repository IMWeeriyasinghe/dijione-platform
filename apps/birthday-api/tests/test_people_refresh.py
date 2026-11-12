"""Phase 1.5 §B — birthday-api proxies BambooHR freshness + a manual
refresh trigger through people-api. In the test suite
``INTEGRATIONS_MODE=mock`` so the employee source is the in-process mock:
freshness reports ``available: false`` and refresh has nothing to do — but
the permission gating and shapes are still exercised.
"""

from __future__ import annotations

from tests.conftest import headers_for


def test_freshness_requires_dashboard_permission(api_client, db):
    resp = api_client.get("/api/birthday/people/freshness", headers=headers_for(1))
    assert resp.status_code == 403


def test_freshness_shape_in_mock_mode(api_client, db):
    resp = api_client.get(
        "/api/birthday/people/freshness", headers=headers_for(1, role="BIRTHDAY_USER")
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["auto_refresh"] == "daily"


def test_manual_refresh_requires_config_manage(api_client, db):
    resp = api_client.post(
        "/api/birthday/people/refresh", headers=headers_for(1, role="BIRTHDAY_USER")
    )
    assert resp.status_code == 403


def test_manual_refresh_conflict_in_mock_mode(api_client, db):
    resp = api_client.post(
        "/api/birthday/people/refresh", headers=headers_for(1, role="BIRTHDAY_ADMIN")
    )
    assert resp.status_code == 409


def test_manual_refresh_proxies_and_audits_when_source_supports_it(api_client, db, platform_calls, monkeypatch):
    """With a source adapter that *does* expose ``request_sync`` (the live
    people-api path), the route returns 202 with the run body and records
    a ``birthday.people.manual_refresh`` audit event."""
    import app.api.routes.employees as employees_route

    class _FakeSource:
        def request_sync(self, *, requested_by_user_id=None):
            return {"run_id": "run-123", "status": "QUEUED"}

    monkeypatch.setattr(employees_route, "get_employee_source", lambda: _FakeSource())

    resp = api_client.post(
        "/api/birthday/people/refresh", headers=headers_for(42, role="BIRTHDAY_ADMIN")
    )
    assert resp.status_code == 202
    assert resp.json()["run_id"] == "run-123"
    actions = [c.get("action") for c in platform_calls["audit_events"]]
    assert "birthday.people.manual_refresh" in actions
