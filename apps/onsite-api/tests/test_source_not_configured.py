"""INTEGRATIONS_MODE=none — an environment with no attendance source yet
(UAT/PROD before go-live): the app runs, nothing is synced or inserted, and
health/freshness say so plainly. No mock data is ever produced."""

import pytest

from app.core.config import get_settings
from app.models.mirror import AttendanceEvent, OnsiteSyncRun, SourceSite
from tests.conftest import headers_for, internal_headers


@pytest.fixture()
def no_source(monkeypatch):
    monkeypatch.setattr(get_settings(), "integrations_mode", "none")


def test_scheduled_and_manual_sync_create_nothing(api_client, db, no_source):
    resp = api_client.post("/api/onsite/internal/scheduled-sync", headers=internal_headers())
    assert resp.status_code == 202 and resp.json()["status"] == "SOURCE_NOT_CONFIGURED"
    resp = api_client.post("/api/onsite/sync", headers=headers_for("ONSITE_ADMIN"))
    assert resp.status_code == 202 and resp.json()["started"] is False
    assert db.query(OnsiteSyncRun).count() == 0
    assert db.query(AttendanceEvent).count() == 0 and db.query(SourceSite).count() == 0


def test_health_and_freshness_report_no_source(api_client, db, no_source):
    deep = api_client.get("/health/deep").json()["checks"]
    assert deep["attendance_source"] == "not_configured" and deep["integrations_mode"] == "none"
    fresh = api_client.get("/api/onsite/freshness", headers=headers_for("ONSITE_VIEWER")).json()
    assert fresh["source_configured"] is False and fresh["sites"] == []
    health = api_client.get("/api/onsite/admin/health", headers=headers_for("ONSITE_ADMIN")).json()
    assert health["source_configured"] is False and health["sites"] == []
    summary = api_client.get("/api/onsite/summary", headers=headers_for("ONSITE_VIEWER")).json()
    assert summary["source_configured"] is False and summary["mirrored_events"] == 0


def test_dashboard_and_exports_without_source(api_client, db, no_source):
    v = headers_for("ONSITE_VIEWER")
    assert api_client.get("/api/onsite/sites", headers=v).json() == []  # UI shows "No enabled sites"
    assert api_client.get("/api/onsite/dashboard/overview", headers=v).status_code == 404  # no enabled site
    assert api_client.get("/api/onsite/today/export", headers=v).status_code == 404  # same rule as the view
    assert api_client.get("/api/onsite/me", headers=v).json()["role"] == "ONSITE_VIEWER"
    ident = api_client.get("/api/onsite/admin/identity-match", headers=headers_for("ONSITE_ADMIN"))
    assert ident.status_code == 200


def test_source_configured_flag(monkeypatch):
    s = get_settings()
    for mode, expected in (("mock", True), ("live", True), ("none", False)):
        monkeypatch.setattr(s, "integrations_mode", mode)
        assert s.source_configured is expected
