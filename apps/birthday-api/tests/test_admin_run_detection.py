"""Admin-triggered detection (plan §7) — calls the exact same
``run_daily_scan`` service the production external scheduler and
``internal.py`` call, gated by user auth (not the internal-service
secret) so it's reachable from the browser for UAT/ops."""

from __future__ import annotations

from tests.conftest import headers_for


def test_admin_run_detection_requires_admin_permission(api_client, db):
    resp = api_client.post(
        "/api/birthday/admin/run-detection", headers=headers_for(1, role="BIRTHDAY_USER"),
    )
    assert resp.status_code == 403


def test_admin_run_detection_returns_scan_summary(api_client, db):
    resp = api_client.post(
        "/api/birthday/admin/run-detection", headers=headers_for(1, role="BIRTHDAY_ADMIN"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "run_id", "status", "employees_scanned", "orders_created", "orders_existing",
        "exceptions", "ineligible_skipped", "errors",
    }
    assert body["status"] == "COMPLETED"
    assert isinstance(body["employees_scanned"], int)


def test_admin_run_detection_defers_safely_when_people_api_is_unreachable(api_client, db, monkeypatch):
    """Architecture Completion Plan Wave E: people-api down -> the scan
    defers (no orders touched), it does not 500, and the run is recorded
    as DEFERRED_SOURCE_UNAVAILABLE."""
    from app.integrations.people_source.client import EmployeeSourceClient, EmployeeSourceUnavailableError

    class _DownClient(EmployeeSourceClient):
        def list_active_employees(self):
            raise EmployeeSourceUnavailableError("people-api unreachable")

        def get_employee(self, employee_id):
            raise EmployeeSourceUnavailableError("people-api unreachable")

    import app.api.routes.admin as admin_module

    monkeypatch.setattr(admin_module, "get_employee_source", lambda: _DownClient())

    resp = api_client.post(
        "/api/birthday/admin/run-detection", headers=headers_for(1, role="BIRTHDAY_ADMIN"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "DEFERRED_SOURCE_UNAVAILABLE"
    assert body["employees_scanned"] == 0
    assert body["orders_created"] == 0


def test_admin_run_detection_is_idempotent_like_the_scheduler_path(api_client, db):
    first = api_client.post(
        "/api/birthday/admin/run-detection", headers=headers_for(1, role="BIRTHDAY_ADMIN"),
    ).json()
    second = api_client.post(
        "/api/birthday/admin/run-detection", headers=headers_for(1, role="BIRTHDAY_ADMIN"),
    ).json()
    assert second["orders_created"] == 0
    assert second["orders_existing"] >= first["orders_created"]
