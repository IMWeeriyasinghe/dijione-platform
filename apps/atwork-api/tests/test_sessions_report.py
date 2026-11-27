"""Interactive sessions report endpoint tests."""
from datetime import UTC, datetime, timedelta

import pytest

from app.api.routes.attendance import get_clock
from app.main import app
from tests.conftest import bearer, issue_token

A = "/api/atwork/attendance"
M = "/api/atwork/management"
MANAGER_PERMS = (
    "atwork.access",
    "atwork.attendance.read_own",
    "atwork.attendance.record_own",
    "atwork.corrections.request_own",
    "atwork.management.access",
    "atwork.attendance.read",
    "atwork.corrections.review",
    "atwork.corrections.approve",
    "atwork.reports.read",
    "atwork.reports.export",
)
EMPLOYEE_PERMS = (
    "atwork.access",
    "atwork.attendance.read_own",
    "atwork.attendance.record_own",
    "atwork.corrections.request_own",
)
_counter = iter(range(5_000_000, 6_000_000))


def rid():
    return f"sess-rpt-{next(_counter)}"


def hdr(user_id=10, permissions=MANAGER_PERMS):
    roles = {"atwork": {"role": "R", "client_id": None, "client_ids": None, "permissions": list(permissions)}}
    return bearer(issue_token(user_id, module_roles=roles))


MGR = hdr()


class FakeClock:
    def __init__(self, start=datetime(2026, 11, 20, 3, 0, tzinfo=UTC)):
        self.value = start

    def __call__(self):
        return self.value

    def advance(self, **kw):
        self.value += timedelta(**kw)


@pytest.fixture()
def clock():
    fake = FakeClock()
    app.dependency_overrides[get_clock] = lambda: fake
    return fake


@pytest.fixture()
def client(api_client, clock):
    return api_client


def checkin(client, clock, user_id=20, hours=2, mode="OFFICE"):
    h = hdr(user_id, EMPLOYEE_PERMS)
    client.post(f"{A}/check-in", json={"work_mode": mode, "client_request_id": rid()}, headers=h)
    clock.advance(hours=hours)
    client.post(f"{A}/check-out", json={"client_request_id": rid()}, headers=h)
    clock.advance(minutes=5)


class TestSessionsReport:
    def test_requires_reports_permission(self, client, clock):
        no_report = hdr(99, EMPLOYEE_PERMS)
        r = client.get(f"{M}/reports/sessions", headers=no_report)
        assert r.status_code == 403

    def test_returns_sessions(self, client, clock):
        checkin(client, clock, user_id=21)
        r = client.get(f"{M}/reports/sessions", headers=MGR)
        assert r.status_code == 200
        d = r.json()
        assert d["total"] >= 1
        assert all("session" in item and "period_totals" in item for item in d["items"])

    def test_pagination(self, client, clock):
        for uid in range(30, 33):
            checkin(client, clock, user_id=uid)
        r = client.get(f"{M}/reports/sessions?limit=2&offset=0", headers=MGR)
        assert r.status_code == 200
        d = r.json()
        assert d["limit"] == 2
        assert len(d["items"]) <= 2

    def test_work_mode_filter(self, client, clock):
        checkin(client, clock, user_id=40, mode="OFFICE")
        checkin(client, clock, user_id=41, mode="REMOTE")
        r = client.get(f"{M}/reports/sessions?work_mode=OFFICE", headers=MGR)
        assert r.status_code == 200
        d = r.json()
        assert all(item["session"]["work_mode"] == "OFFICE" for item in d["items"])

    def test_period_totals_separate_from_session(self, client, clock):
        checkin(client, clock, user_id=50, hours=3)
        r = client.get(f"{M}/reports/sessions", headers=MGR)
        assert r.status_code == 200
        for item in r.json()["items"]:
            totals = item["period_totals"]
            assert "gross_seconds" in totals
            assert "net_seconds" in totals
            assert totals["gross_seconds"] >= 0

    def test_date_range_filter(self, client, clock):
        checkin(client, clock, user_id=60)
        r = client.get(f"{M}/reports/sessions?date_from=2000-01-01&date_to=2000-01-01", headers=MGR)
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_response_includes_time_zone(self, client, clock):
        r = client.get(f"{M}/reports/sessions", headers=MGR)
        assert r.status_code == 200
        d = r.json()
        assert "time_zone" in d
        assert d["time_zone"]
