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
        "run_id", "employees_scanned", "orders_created", "orders_existing",
        "exceptions", "ineligible_skipped", "errors",
    }
    assert isinstance(body["employees_scanned"], int)


def test_admin_run_detection_is_idempotent_like_the_scheduler_path(api_client, db):
    first = api_client.post(
        "/api/birthday/admin/run-detection", headers=headers_for(1, role="BIRTHDAY_ADMIN"),
    ).json()
    second = api_client.post(
        "/api/birthday/admin/run-detection", headers=headers_for(1, role="BIRTHDAY_ADMIN"),
    ).json()
    assert second["orders_created"] == 0
    assert second["orders_existing"] >= first["orders_created"]
