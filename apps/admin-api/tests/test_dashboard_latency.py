"""The Admin dashboard reads Platform Core and talent-api in parallel and never waits
longer than the talent budget for the best-effort pending count."""

import threading
import time

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.services import platform_gateway, talent_gateway

VALID = {"Authorization": "Bearer valid-admin-token"}
INVALID = {"Authorization": "Bearer not-an-admin"}
COUNTS = {
    "total_users": 3, "active_users": 3, "super_admins": 1, "platform_admins": 0,
    "active_modules": 5, "pending_talent_requests": 0,
}


class FakePlatform:
    def __init__(self, delay: float = 0.0, status: int = 200):
        self.delay, self.status, self.started = delay, status, None

    def request_admin(self, method, path, *, bearer_token, json=None, params=None):
        self.started = time.perf_counter()
        time.sleep(self.delay)
        if bearer_token != "valid-admin-token":
            return httpx.Response(403, json={"detail": "Platform admin access required"})
        return httpx.Response(self.status, json=dict(COUNTS))


class FakeTalent:
    def __init__(self, delay: float = 0.0, pending: int = 4):
        self.delay, self.pending, self.started, self.calls = delay, pending, None, 0
        self.release = threading.Event()

    def get_internal(self, path, *, params=None):
        self.calls += 1
        self.started = time.perf_counter()
        self.release.wait(self.delay)
        return httpx.Response(200, json={"pending_requests": self.pending}, request=httpx.Request("GET", path))


def _call(platform, talent, headers=VALID):
    app.dependency_overrides[platform_gateway.get_platform_client] = lambda: platform
    app.dependency_overrides[talent_gateway.get_talent_client] = lambda: talent
    try:
        started = time.perf_counter()
        resp = TestClient(app).get("/api/admin/dashboard", headers=headers)
        return resp, time.perf_counter() - started
    finally:
        app.dependency_overrides.clear()


def test_platform_and_talent_reads_run_in_parallel():
    platform, talent = FakePlatform(delay=0.6), FakeTalent(delay=0.6)
    resp, elapsed = _call(platform, talent)
    assert resp.status_code == 200
    assert resp.json()["pending_talent_requests"] == 4
    assert resp.json()["total_users"] == 3
    # Sequential would be >= 1.2 s; parallel is about 0.6 s.
    assert elapsed < 1.1, elapsed
    assert abs(platform.started - talent.started) < 0.3


def test_slow_talent_api_never_holds_the_dashboard_beyond_its_budget(monkeypatch):
    monkeypatch.setattr(talent_gateway, "TALENT_SUMMARY_BUDGET_SECONDS", 0.3)
    talent = FakeTalent(delay=5.0)
    try:
        resp, elapsed = _call(FakePlatform(), talent)
        assert resp.status_code == 200
        assert resp.json()["pending_talent_requests"] == 0  # degraded, as for an outage
        assert resp.json()["total_users"] == 3
        assert elapsed < 1.5, elapsed
    finally:
        talent.release.set()  # let the background read finish


def test_platform_refusal_is_still_returned_and_no_counts_leak():
    resp, _ = _call(FakePlatform(), FakeTalent(), headers=INVALID)
    assert resp.status_code == 403
    assert "pending_talent_requests" not in resp.text


def test_missing_token_is_refused_before_any_downstream_call():
    talent = FakeTalent()
    resp, _ = _call(FakePlatform(), talent, headers={})
    assert resp.status_code == 401
    assert talent.calls == 0


def test_talent_client_timeout_is_bounded():
    assert talent_gateway.get_talent_client()._timeout == talent_gateway.TALENT_SUMMARY_BUDGET_SECONDS <= 3.0
