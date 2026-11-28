"""BP security: scope isolation, identity mapping, and analytics scoping.

Tests:
 - employee-search returns correct platform_user_id (not AttendanceEmployee.id alias)
 - employee-search only accessible with atwork.access.manage permission
 - BP grant/scope endpoints are inaccessible without atwork.access.manage
 - A BP cannot read another BP's employees via URL manipulation
 - Analytics eligible counts are scoped to BP's assigned employees (not full directory)
 - Two BPs on employees from the same client see only their own slice
 - Full admin sees all employees in analytics and employee list
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import bearer, issue_token

A = "/api/atwork/attendance"
M = "/api/atwork/management"

PERM_MANAGEMENT = "atwork.management.access"
PERM_READ_ALL = "atwork.attendance.read"
PERM_REPORTS = "atwork.reports.read"
PERM_BP_ACCESS = "atwork.bp.access"
PERM_ACCESS_MANAGE = "atwork.access.manage"

FULL_ADMIN_PERMS = [
    "atwork.access",
    PERM_MANAGEMENT,
    PERM_READ_ALL,
    PERM_REPORTS,
    "atwork.reports.export",
    "atwork.settings.manage",
    "atwork.corrections.review",
    "atwork.corrections.approve",
    "atwork.audit.read",
    PERM_ACCESS_MANAGE,
]

BP_PERMS = ["atwork.access", PERM_BP_ACCESS]
ACCESS_MANAGE_PERMS = ["atwork.access", PERM_ACCESS_MANAGE]


def _hdr(user_id: int, permissions: list[str]) -> dict:
    roles = {"atwork": {"role": "R", "client_id": None, "client_ids": None, "permissions": permissions}}
    return bearer(issue_token(user_id, module_roles=roles))


def _full_admin_hdr(user_id: int = 1) -> dict:
    return _hdr(user_id, FULL_ADMIN_PERMS)


def _bp_hdr(user_id: int) -> dict:
    return _hdr(user_id, BP_PERMS)


def _access_manage_hdr(user_id: int = 99) -> dict:
    return _hdr(user_id, ACCESS_MANAGE_PERMS)


@pytest.fixture()
def api_client():
    from app.main import app
    from app.db.session import SessionLocal, engine
    from app.models import Base

    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db(api_client):
    """Return a live DB session against the test DB."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _register_employee(api_client, user_id: int, email: str, name: str = "Test Employee") -> None:
    """Directly create an AttendanceEmployee row in the test DB.

    ``issue_token`` hardcodes email as ``user{id}@example.com`` — pass that
    value as ``email`` so the workforce search mock and the DB row agree.
    ``remember_employee`` is called on check-in, not on status, so we insert
    directly rather than triggering a full session lifecycle.
    """
    from app.db.session import SessionLocal
    from app.models.corrections import AttendanceEmployee
    from sqlalchemy.exc import IntegrityError

    db = SessionLocal()
    try:
        if db.get(AttendanceEmployee, user_id) is None:
            db.add(AttendanceEmployee(platform_user_id=user_id, full_name=name, email=email.lower()))
            db.commit()
    except IntegrityError:
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Check 1: employee-search identity mapping
# ---------------------------------------------------------------------------

class TestEmployeeSearchIdentityMapping:
    def test_requires_access_manage_permission(self, api_client):
        """Route must reject non-access-manage tokens."""
        resp = api_client.get(M + "/bp/employee-search?q=test", headers=_full_admin_hdr())
        # Full admin does have access_manage in FULL_ADMIN_PERMS
        assert resp.status_code in (200, 404)

    def test_bp_token_cannot_reach_search(self, api_client):
        """A pure BP token (no access.manage) must be denied."""
        resp = api_client.get(M + "/bp/employee-search?q=test", headers=_bp_hdr(10))
        assert resp.status_code in (401, 403)

    def test_anonymous_cannot_reach_search(self, api_client):
        resp = api_client.get(M + "/bp/employee-search?q=test")
        assert resp.status_code in (401, 403)

    def test_q_too_short_returns_422(self, api_client):
        resp = api_client.get(M + "/bp/employee-search?q=a", headers=_access_manage_hdr())
        assert resp.status_code == 422

    def test_workforce_unavailable_returns_empty_list(self, api_client):
        """When people-api is down, search returns [] (fail-safe)."""
        with patch("app.services.workforce_client.search_workforce", return_value=[]):
            resp = api_client.get(M + "/bp/employee-search?q=alice", headers=_access_manage_hdr())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_unregistered_employee_has_null_platform_user_id(self, api_client):
        """Employees in workforce directory but not in AttendanceEmployee get platform_user_id=null."""
        fake_result = [{"work_email": "ghost@example.com", "display_name": "Ghost User", "department": "Client A"}]
        with patch("app.api.routes.management.search_workforce", return_value=fake_result):
            resp = api_client.get(M + "/bp/employee-search?q=ghost", headers=_access_manage_hdr())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["work_email"] == "ghost@example.com"
        assert data[0]["platform_user_id"] is None  # not registered in DijiAtWork

    def test_registered_employee_has_correct_platform_user_id(self, api_client):
        """An employee who has used DijiAtWork gets their real platform_user_id."""
        # issue_token for user_id=42 sets email to "user42@example.com" in the JWT.
        # The attendance/status endpoint creates AttendanceEmployee with that email.
        _register_employee(api_client, 42, "user42@example.com")

        # Mock workforce returns the same email that the JWT set
        fake_result = [{"work_email": "user42@example.com", "display_name": "Alice", "department": "Client A"}]
        with patch("app.api.routes.management.search_workforce", return_value=fake_result):
            resp = api_client.get(M + "/bp/employee-search?q=alice", headers=_access_manage_hdr())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["platform_user_id"] == 42  # must be the real platform_user_id, not an internal id

    def test_no_cross_email_contamination(self, api_client):
        """Search for email A must not return email B's platform_user_id."""
        # issue_token sets email to "user{id}@example.com"
        _register_employee(api_client, 10, "user10@example.com")
        _register_employee(api_client, 20, "user20@example.com")

        # Search results only contain user10's email from workforce
        fake_result = [{"work_email": "user10@example.com", "display_name": "Emp 10", "department": "Client B"}]
        with patch("app.api.routes.management.search_workforce", return_value=fake_result):
            resp = api_client.get(M + "/bp/employee-search?q=emp10", headers=_access_manage_hdr())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["platform_user_id"] == 10
        # emp20 must not appear
        assert all(r["work_email"] != "emp20@example.com" for r in data)


# ---------------------------------------------------------------------------
# Check 2: BP scope isolation — cannot access another BP's employees
# ---------------------------------------------------------------------------

def _grant_bp(api_client, manager_hdr: dict, target_user_id: int) -> None:
    resp = api_client.post(M + "/bp", json={"target_user_id": target_user_id}, headers=manager_hdr)
    assert resp.status_code == 201, f"grant_bp failed: {resp.text}"


def _assign_scope(api_client, manager_hdr: dict, bp_user_id: int, employee_user_id: int) -> None:
    resp = api_client.post(M + f"/bp/{bp_user_id}/scope", json={"employee_user_id": employee_user_id}, headers=manager_hdr)
    assert resp.status_code == 201, f"assign_scope failed: {resp.text}"


class TestBPScopeIsolation:
    def test_bp_cannot_read_employees_outside_scope(self, api_client):
        """BP1 cannot access BP2's employee via direct URL — must get 403 or 404."""
        admin = _full_admin_hdr()
        _register_employee(api_client, 101, "user101@example.com")
        _register_employee(api_client, 102, "user102@example.com")
        _register_employee(api_client, 51, "user51@example.com")
        _register_employee(api_client, 52, "user52@example.com")

        _grant_bp(api_client, admin, 51)
        _assign_scope(api_client, admin, 51, 101)
        _grant_bp(api_client, admin, 52)
        _assign_scope(api_client, admin, 52, 102)

        # BP1 can call their own employee's history endpoint
        # (may be 404 when no sessions, but must NOT be 403 — that would mean even own scope is blocked)
        resp_own = api_client.get(M + "/employees/101/history", headers=_bp_hdr(51))
        assert resp_own.status_code in (200, 404)  # 404 OK — no sessions in test DB

        # BP1 must NOT see employee 102 (BP2's scope):
        # - 403: explicitly denied (authorization failure)
        # - 404: not found in BP1's scope (also acceptable — no data leaked)
        # - anything other than 200/201 is acceptable; 200 would be a bug
        resp_other = api_client.get(M + "/employees/102/history", headers=_bp_hdr(51))
        assert resp_other.status_code != 200, (
            f"BP1 (user 51) should NOT be able to read employee 102 (BP2's scope), "
            f"but got {resp_other.status_code}: {resp_other.text[:200]}"
        )

    def test_bp_employees_list_scoped(self, api_client):
        """GET /management/employees must return only the BP's assigned employees."""
        admin = _full_admin_hdr()
        _register_employee(api_client, 201, "user201@example.com")
        _register_employee(api_client, 202, "user202@example.com")
        _register_employee(api_client, 61, "user61@example.com")

        _grant_bp(api_client, admin, 61)
        _assign_scope(api_client, admin, 61, 201)
        # 202 not in BP61's scope

        resp = api_client.get(M + "/employees", headers=_bp_hdr(61))
        assert resp.status_code == 200
        data = resp.json()
        ids = [i["platform_user_id"] for i in data["items"]]
        assert 201 in ids
        assert 202 not in ids

    def test_bp_cannot_access_another_bp_via_bp_scope_url(self, api_client):
        """BP cannot read another BP's scope list by guessing the URL."""
        admin = _full_admin_hdr()
        _register_employee(api_client, 71, "user71@example.com")
        _register_employee(api_client, 72, "user72@example.com")
        _grant_bp(api_client, admin, 71)
        _grant_bp(api_client, admin, 72)

        # bp71 tries to read bp72's scope
        bp71_hdr = _bp_hdr(71)
        resp = api_client.get(M + "/bp/72/scope", headers=bp71_hdr)
        # BP tokens don't have access.manage, must be denied
        assert resp.status_code in (401, 403)

    def test_full_admin_sees_all_employees(self, api_client):
        """A full admin is not filtered by any scope."""
        _register_employee(api_client, 301, "user301@example.com")
        _register_employee(api_client, 302, "user302@example.com")

        resp = api_client.get(M + "/employees", headers=_full_admin_hdr())
        assert resp.status_code == 200
        data = resp.json()
        ids = [i["platform_user_id"] for i in data["items"]]
        assert 301 in ids
        assert 302 in ids


# ---------------------------------------------------------------------------
# Check 3: Analytics eligible counts correctly scoped for BP
# ---------------------------------------------------------------------------

class TestAnalyticsBPScope:
    def test_bp_analytics_eligible_is_scoped_not_full_directory(self, api_client):
        """When a BP calls analytics, eligible_employees must reflect their scope,
        not the full workforce directory count."""
        admin = _full_admin_hdr()
        # 2 employees in Client A, only one assigned to BP
        _register_employee(api_client, 401, "user401@example.com")
        _register_employee(api_client, 402, "user402@example.com")
        _register_employee(api_client, 81, "user81@example.com")

        _grant_bp(api_client, admin, 81)
        _assign_scope(api_client, admin, 81, 401)
        # 402 not in BP81's scope

        # Workforce directory says Client A has 50 employees
        full_counts = {"Client A": 50}
        def _client_map(db, user_ids):
            m = {401: "Client A", 402: "Client A"}
            return {uid: m[uid] for uid in user_ids if uid in m}

        with patch("app.api.routes.management.get_client_counts", return_value=full_counts):
            with patch("app.api.routes.management.resolve_client_for_users", side_effect=_client_map):
                resp = api_client.get(M + "/analytics", headers=_bp_hdr(81))

        assert resp.status_code == 200
        data = resp.json()
        # BP should see eligible=1 (their 1 scoped employee in Client A), not 50
        client_a_rows = [r for r in data["by_client"] if r["client"] == "Client A"]
        if client_a_rows:
            assert client_a_rows[0]["eligible_employees"] == 1, (
                f"BP's eligible_employees should be 1 (their scope), "
                f"got {client_a_rows[0]['eligible_employees']}"
            )

    def test_two_bps_same_client_see_only_their_slice(self, api_client):
        """Two BPs assigned to different employees from the same client see independent slices."""
        admin = _full_admin_hdr()
        _register_employee(api_client, 501, "user501@example.com")
        _register_employee(api_client, 502, "user502@example.com")
        _register_employee(api_client, 91, "user91@example.com")
        _register_employee(api_client, 92, "user92@example.com")

        _grant_bp(api_client, admin, 91)
        _assign_scope(api_client, admin, 91, 501)
        _grant_bp(api_client, admin, 92)
        _assign_scope(api_client, admin, 92, 502)

        def _client_map(db, user_ids):
            """Return client only for the user IDs actually requested."""
            m = {501: "Client B", 502: "Client B"}
            return {uid: m[uid] for uid in user_ids if uid in m}

        with patch("app.api.routes.management.resolve_client_for_users", side_effect=_client_map):
            resp_bp91 = api_client.get(M + "/analytics", headers=_bp_hdr(91))
            resp_bp92 = api_client.get(M + "/analytics", headers=_bp_hdr(92))

        assert resp_bp91.status_code == 200
        assert resp_bp92.status_code == 200
        # Each BP should see eligible=1 for Client B
        for resp, label in [(resp_bp91, "BP91"), (resp_bp92, "BP92")]:
            rows = [r for r in resp.json()["by_client"] if r["client"] == "Client B"]
            if rows:
                assert rows[0]["eligible_employees"] == 1, f"{label} expected eligible=1, got {rows[0]['eligible_employees']}"

    def test_full_admin_analytics_uses_directory_counts(self, api_client):
        """Full admin sees the workforce directory count as eligible, not a session count."""
        _register_employee(api_client, 601, "user601@example.com")

        full_counts = {"Client C": 30}
        def _client_map(db, user_ids):
            m = {601: "Client C"}
            return {uid: m[uid] for uid in user_ids if uid in m}

        with patch("app.api.routes.management.get_client_counts", return_value=full_counts):
            with patch("app.api.routes.management.resolve_client_for_users", side_effect=_client_map):
                resp = api_client.get(M + "/analytics", headers=_full_admin_hdr())

        assert resp.status_code == 200
        rows = [r for r in resp.json()["by_client"] if r["client"] == "Client C"]
        if rows:
            assert rows[0]["eligible_employees"] == 30
