import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.api.routes.attendance import get_clock
from app.main import app
from app.models.attendance import AttendanceBreak, AttendanceEvent, AttendanceSession
from app.models.corrections import CorrectionRequest
from tests.conftest import bearer, issue_token

A = "/api/atwork/attendance"
C = "/api/atwork/corrections"
M = "/api/atwork/management"
EMPLOYEE = (
    "atwork.access",
    "atwork.attendance.read_own",
    "atwork.attendance.record_own",
    "atwork.corrections.request_own",
)
MGMT = "atwork.management.access"
MANAGER = (
    *EMPLOYEE,
    MGMT,
    "atwork.attendance.read",
    "atwork.corrections.review",
    "atwork.corrections.approve",
    "atwork.reports.read",
    "atwork.reports.export",
    "atwork.settings.manage",
    "atwork.audit.read",
)
counter = iter(range(10_000_000))


def rid():
    return f"corr-test-{next(counter)}"


def hdr(user_id=7, permissions=EMPLOYEE, name="Test User"):
    roles = {"atwork": {"role": "R", "client_id": None, "client_ids": None, "permissions": list(permissions)}}
    return bearer(issue_token(user_id, module_roles=roles))


MGR = hdr(99, MANAGER)


class Clock:
    def __init__(self):
        self.value = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)

    def __call__(self):
        return self.value

    def advance(self, **kw):
        self.value += timedelta(**kw)


@pytest.fixture()
def clock():
    fake = Clock()
    app.dependency_overrides[get_clock] = lambda: fake
    return fake


def post(client, path, h=None, **body):
    return client.post(path, json=body, headers=h or hdr())


def work(client, clock, user=7, hours=2, mode="OFFICE"):
    h = hdr(user)
    session = post(client, f"{A}/check-in", h, work_mode=mode, client_request_id=rid()).json()["session"]
    clock.advance(hours=hours)
    post(client, f"{A}/check-out", h, client_request_id=rid())
    clock.advance(minutes=30)
    return session["id"]


def iso(clock_value, **kw):
    return (clock_value + timedelta(**kw)).isoformat()


def amend(client, session_id, h=None, **body):
    body.setdefault("reason", "Forgot to record correctly")
    body.setdefault("client_request_id", rid())
    return post(client, C, h, session_id=session_id, **body)


def base(clock):
    return datetime(2026, 11, 9, 3, 0, tzinfo=UTC)


def test_request_does_not_change_official_record_until_approved(api_client, clock, db):
    sid = work(api_client, clock)
    r = amend(api_client, sid, check_in_at=iso(base(clock), minutes=-30), work_mode="REMOTE")
    assert r.status_code == 201 and r.json()["status"] == "PENDING"
    assert r.json()["original"]["work_mode"] == "OFFICE"
    assert api_client.get(f"{A}/sessions/{sid}", headers=hdr()).json()["work_mode"] == "OFFICE"

    done = post(api_client, f"{M}/corrections/{r.json()['id']}/approve", MGR, note="ok")
    assert done.status_code == 200 and done.json()["status"] == "APPROVED"
    session = api_client.get(f"{A}/sessions/{sid}", headers=hdr()).json()
    assert session["work_mode"] == "REMOTE"
    assert session["totals"]["gross_seconds"] == 9000
    assert session["correction_count"] == 1
    actions = [e.action for e in db.scalars(select(AttendanceEvent).order_by(AttendanceEvent.occurred_at))]
    assert {"CORRECTION_REQUESTED", "SESSION_CORRECTED", "CORRECTION_APPROVED"} <= set(actions)
    event = db.scalars(select(AttendanceEvent).where(AttendanceEvent.action == "SESSION_CORRECTED")).one()
    assert event.before_state["work_mode"] == "OFFICE" and event.after_state["work_mode"] == "REMOTE"
    assert event.actor_user_id == 99 and event.subject_user_id == 7


def test_break_correction_preserves_the_replaced_break(api_client, clock, db):
    h = hdr()
    sid = post(api_client, f"{A}/check-in", h, work_mode="OFFICE", client_request_id=rid()).json()["session"]["id"]
    clock.advance(minutes=30)
    post(api_client, f"{A}/breaks/start", h, client_request_id=rid())
    clock.advance(minutes=30)
    post(api_client, f"{A}/breaks/end", h, client_request_id=rid())
    clock.advance(minutes=60)
    post(api_client, f"{A}/check-out", h, client_request_id=rid())
    b = base(clock)
    r = amend(api_client, sid, breaks=[{"started_at": iso(b, minutes=10), "ended_at": iso(b, minutes=20)}]).json()
    assert post(api_client, f"{M}/corrections/{r['id']}/approve", MGR).status_code == 200
    session = api_client.get(f"{A}/sessions/{sid}", headers=h).json()
    assert len(session["breaks"]) == 1 and session["totals"]["break_seconds"] == 600
    rows = db.scalars(select(AttendanceBreak).where(AttendanceBreak.session_id == sid)).all()
    assert len(rows) == 2
    assert sum(1 for row in rows if row.voided_at is not None) == 1


def test_missed_checkout_is_completed_through_correction(api_client, clock):
    h = hdr()
    sid = post(api_client, f"{A}/check-in", h, work_mode="OFFICE", client_request_id=rid()).json()["session"]["id"]
    clock.advance(hours=20)
    r = amend(api_client, sid, check_out_at=iso(base(clock), hours=8)).json()
    assert post(api_client, f"{M}/corrections/{r['id']}/approve", MGR).status_code == 200
    assert api_client.get(f"{A}/status", headers=h).json()["state"] == "NOT_CHECKED_IN"
    assert post(api_client, f"{A}/check-in", h, work_mode="REMOTE", client_request_id=rid()).status_code == 200


def test_missing_session_is_created_only_on_approval(api_client, clock):
    b = base(clock) - timedelta(days=2)
    r = post(
        api_client,
        C,
        reason="Forgot my phone that day",
        client_request_id=rid(),
        work_mode="CLIENT_SITE",
        check_in_at=b.isoformat(),
        check_out_at=iso(b, hours=8),
        breaks=[{"started_at": iso(b, hours=4), "ended_at": iso(b, hours=5)}],
    )
    assert r.status_code == 201 and r.json()["kind"] == "CREATE_MISSING" and r.json()["session_id"] is None
    assert api_client.get(f"{A}/history", headers=hdr()).json()["total"] == 0
    assert post(api_client, f"{M}/corrections/{r.json()['id']}/approve", MGR).status_code == 200
    history = api_client.get(f"{A}/history", headers=hdr()).json()
    assert history["total"] == 1
    session = history["sessions"][0]
    assert session["origin"] == "CORRECTION" and session["totals"]["net_seconds"] == 7 * 3600


def test_one_pending_request_per_session_and_withdraw(api_client, clock):
    sid = work(api_client, clock)
    first = amend(api_client, sid, work_mode="REMOTE").json()
    second = amend(api_client, sid, work_mode="CLIENT_SITE")
    assert second.status_code == 409 and second.json()["code"] == "CORRECTION_ALREADY_PENDING"
    other = hdr(8)
    assert post(api_client, f"{C}/{first['id']}/withdraw", other).status_code == 404
    assert post(api_client, f"{C}/{first['id']}/withdraw").json()["status"] == "WITHDRAWN"
    assert post(api_client, f"{C}/{first['id']}/withdraw").json()["code"] == "CORRECTION_NOT_PENDING"
    assert amend(api_client, sid, work_mode="CLIENT_SITE").status_code == 201


def test_submit_is_idempotent(api_client, clock):
    sid = work(api_client, clock)
    key = rid()
    a = amend(api_client, sid, work_mode="REMOTE", client_request_id=key)
    b = amend(api_client, sid, work_mode="REMOTE", client_request_id=key)
    assert a.status_code == b.status_code == 201 and a.json()["id"] == b.json()["id"]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"check_in_at": (datetime(2026, 11, 10, tzinfo=UTC)).isoformat()}, "CORRECTION_INVALID"),
        ({"check_out_at": datetime(2026, 11, 9, 2, tzinfo=UTC).isoformat()}, "CORRECTION_INVALID"),
        (
            {
                "breaks": [
                    {"started_at": "2026-11-09T03:10:00+00:00", "ended_at": "2026-11-09T03:40:00+00:00"},
                    {"started_at": "2026-11-09T03:30:00+00:00", "ended_at": "2026-11-09T03:50:00+00:00"},
                ]
            },
            "CORRECTION_INVALID",
        ),
        (
            {"breaks": [{"started_at": "2026-11-09T02:00:00+00:00", "ended_at": "2026-11-09T03:10:00+00:00"}]},
            "CORRECTION_INVALID",
        ),
        ({"work_mode": "OFFICE"}, "CORRECTION_NO_CHANGES"),
    ],
)
def test_invalid_corrections_are_rejected(api_client, clock, change, code):
    sid = work(api_client, clock)
    r = amend(api_client, sid, **change)
    assert r.status_code == 422 and r.json()["code"] == code


def test_same_second_session_can_still_be_corrected(api_client, clock):
    h = hdr()
    sid = post(api_client, f"{A}/check-in", h, work_mode="OFFICE", client_request_id=rid()).json()["session"]["id"]
    post(api_client, f"{A}/check-out", h, client_request_id=rid())
    assert amend(api_client, sid, work_mode="REMOTE").status_code == 201


def test_overlap_with_another_session_is_rejected(api_client, clock):
    first = work(api_client, clock)
    second = work(api_client, clock)
    assert first != second
    r = amend(api_client, second, check_in_at=iso(base(clock), hours=1))
    assert r.status_code == 409 and r.json()["code"] == "SESSION_OVERLAP"


def test_managers_cannot_decide_their_own_corrections(api_client, clock):
    h = hdr(99, MANAGER)
    sid = work_as_manager(api_client, clock, h)
    r = amend(api_client, sid, h, work_mode="REMOTE").json()
    assert r["can_decide"] is False
    for path, body in (("approve", {}), ("reject", {"reason": "Not allowed"})):
        denied = post(api_client, f"{M}/corrections/{r['id']}/{path}", h, **body)
        assert denied.status_code == 403 and denied.json()["code"] == "SELF_DECISION_FORBIDDEN"
    assert api_client.get(f"{M}/corrections/{r['id']}", headers=h).json()["can_decide"] is False


def work_as_manager(client, clock, h):
    sid = post(client, f"{A}/check-in", h, work_mode="OFFICE", client_request_id=rid()).json()["session"]["id"]
    clock.advance(hours=1)
    post(client, f"{A}/check-out", h, client_request_id=rid())
    return sid


def test_rejection_requires_a_reason_and_leaves_records(api_client, clock):
    sid = work(api_client, clock)
    r = amend(api_client, sid, work_mode="REMOTE").json()
    assert post(api_client, f"{M}/corrections/{r['id']}/reject", MGR, reason="x").status_code == 422
    out = post(api_client, f"{M}/corrections/{r['id']}/reject", MGR, reason="No evidence given").json()
    assert out["status"] == "REJECTED" and out["decision_note"] == "No evidence given"
    assert api_client.get(f"{A}/sessions/{sid}", headers=hdr()).json()["work_mode"] == "OFFICE"
    assert post(api_client, f"{M}/corrections/{r['id']}/approve", MGR).json()["code"] == "CORRECTION_NOT_PENDING"


def test_stale_request_cannot_overwrite_later_changes(api_client, clock):
    h = hdr()
    sid = post(api_client, f"{A}/check-in", h, work_mode="OFFICE", client_request_id=rid()).json()["session"]["id"]
    clock.advance(hours=1)
    r = amend(api_client, sid, work_mode="REMOTE").json()
    post(api_client, f"{A}/breaks/start", h, client_request_id=rid())
    out = post(api_client, f"{M}/corrections/{r['id']}/approve", MGR)
    assert out.status_code == 409 and out.json()["code"] == "CORRECTION_STALE"


def test_concurrent_approvals_apply_once(api_client, clock, db):
    sid = work(api_client, clock)
    r = amend(api_client, sid, work_mode="REMOTE").json()
    managers = [hdr(90 + i, MANAGER) for i in range(6)]
    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(lambda h: post(api_client, f"{M}/corrections/{r['id']}/approve", h).status_code, managers))
    assert sorted(codes) == [200, 409, 409, 409, 409, 409]
    assert len(db.scalars(select(AttendanceEvent).where(AttendanceEvent.action == "SESSION_CORRECTED")).all()) == 1
    assert db.get(AttendanceSession, sid).correction_count == 1


def test_concurrent_overlapping_missing_sessions_cannot_both_be_approved(api_client, clock, db):
    b = base(clock) - timedelta(days=3)
    ids = []
    for offset in (0, 30):
        request = CorrectionRequest(
            platform_user_id=7,
            kind="CREATE_MISSING",
            status="PENDING",
            reason="seeded",
            client_request_id=rid(),
            proposed={
                "work_mode": "OFFICE",
                "check_in_at": iso(b, minutes=offset),
                "check_out_at": iso(b, hours=2, minutes=offset),
                "breaks": [],
            },
        )
        db.add(request)
        db.commit()
        ids.append(request.id)
    with ThreadPoolExecutor(2) as pool:
        codes = list(pool.map(lambda i: post(api_client, f"{M}/corrections/{i}/approve", MGR).status_code, ids))
    assert sorted(codes) == [200, 409]


@pytest.mark.parametrize(
    ("method", "path", "permission"),
    [
        ("get", "/overview", "atwork.attendance.read"),
        ("get", "/employees", "atwork.attendance.read"),
        ("get", "/corrections", "atwork.corrections.review"),
        ("get", "/audit", "atwork.audit.read"),
        ("get", "/reports/summary", "atwork.reports.read"),
        ("get", "/settings", "atwork.settings.manage"),
        ("post", "/corrections/x/approve", "atwork.corrections.approve"),
    ],
)
def test_management_needs_access_and_the_specific_permission(api_client, method, path, permission):
    call = getattr(api_client, method)
    kw = {"json": {}} if method == "post" else {}
    url = f"{M}{path}"
    assert call(url, headers=hdr(50, EMPLOYEE), **kw).status_code == 403
    assert call(url, headers=hdr(50, (MGMT,)), **kw).status_code == 403
    assert call(url, headers=hdr(50, (permission,)), **kw).status_code == 403
    assert call(url, headers=hdr(50, (MGMT, permission)), **kw).status_code != 403


def test_export_needs_both_export_and_report_permissions(api_client):
    url = f"{M}/reports/export?report=sessions&format=csv"
    assert api_client.get(url, headers=hdr(50, (MGMT, "atwork.reports.export"))).status_code == 403
    assert api_client.get(url, headers=hdr(50, (MGMT, "atwork.reports.read"))).status_code == 403
    assert api_client.get(url, headers=hdr(50, (MGMT, "atwork.reports.read", "atwork.reports.export"))).status_code == 200


def test_open_break_needs_an_end_time_in_a_correction(api_client, clock):
    h = hdr()
    sid = post(api_client, f"{A}/check-in", h, work_mode="OFFICE", client_request_id=rid()).json()["session"]["id"]
    clock.advance(minutes=10)
    post(api_client, f"{A}/breaks/start", h, client_request_id=rid())
    clock.advance(minutes=10)
    r = amend(api_client, sid, work_mode="REMOTE")
    assert r.status_code == 422 and r.json()["code"] == "CORRECTION_INVALID"


def test_excel_export_survives_control_characters_in_a_reason(api_client, clock):
    sid = work(api_client, clock)
    assert amend(api_client, sid, work_mode="REMOTE", reason="Bad \x01 character").status_code == 201
    params = {"report": "corrections", "format": "xlsx", "date_from": "2026-11-09", "date_to": "2026-11-09"}
    out = api_client.get(f"{M}/reports/export", params=params, headers=MGR)
    assert out.status_code == 200
    rows = list(load_workbook(io.BytesIO(out.content)).active.iter_rows(values_only=True))
    assert rows[1][10] == "Bad  character"


def test_concurrent_settings_updates_keep_one_winner(api_client, clock):
    current = api_client.get(f"{M}/settings", headers=MGR).json()
    bodies = [{**current, "missed_checkout_hours": hours} for hours in range(2, 8)]
    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(lambda b: api_client.put(f"{M}/settings", json=b, headers=MGR).status_code, bodies))
    assert sorted(codes) == [200, 409, 409, 409, 409, 409]
    assert api_client.get(f"{M}/settings", headers=MGR).json()["version"] == 1


def test_concurrent_approvals_of_two_sessions_cannot_overlap(api_client, clock):
    first, second = work(api_client, clock), work(api_client, clock)
    b = base(clock)
    a = amend(api_client, first, check_out_at=iso(b, hours=2, minutes=20)).json()
    c = amend(api_client, second, check_in_at=iso(b, hours=2, minutes=10)).json()
    with ThreadPoolExecutor(2) as pool:
        codes = list(pool.map(lambda i: post(api_client, f"{M}/corrections/{i}/approve", MGR).status_code, [a["id"], c["id"]]))
    assert sorted(codes) == [200, 409]


def test_employee_cannot_see_another_employees_correction(api_client, clock):
    sid = work(api_client, clock)
    r = amend(api_client, sid, work_mode="REMOTE").json()
    assert api_client.get(f"{C}/{r['id']}", headers=hdr(8)).status_code == 404
    assert amend(api_client, sid, hdr(8), work_mode="REMOTE").status_code == 404
    assert api_client.get(C, headers=hdr(8)).json()["total"] == 0


def test_overview_employee_search_and_history(api_client, clock):
    work(api_client, clock, user=7)
    post(api_client, f"{A}/check-in", hdr(8), work_mode="REMOTE", client_request_id=rid())
    h9 = hdr(9)
    post(api_client, f"{A}/check-in", h9, work_mode="OFFICE", client_request_id=rid())
    post(api_client, f"{A}/breaks/start", h9, client_request_id=rid())
    clock.advance(hours=12, minutes=30)  # 23:30 in Colombo, still the same local day
    data = api_client.get(f"{M}/overview", headers=MGR).json()
    assert (data["working_count"], data["on_break_count"], data["completed_today"]) == (1, 1, 1)
    assert data["exception_count"] == 2 and data["pending_corrections"] == 0
    assert data["working"][0]["overdue"] is True
    found = api_client.get(f"{M}/employees", params={"q": "user8"}, headers=MGR).json()
    assert [e["platform_user_id"] for e in found["items"]] == [8]
    assert found["items"][0]["state"] == "WORKING"
    assert api_client.get(f"{M}/employees/7/attendance", headers=MGR).json()["total"] == 1
    assert api_client.get(f"{M}/employees/12345/attendance", headers=MGR).status_code == 404


def test_overdue_sessions_are_flagged_but_never_closed(api_client, clock):
    post(api_client, f"{A}/check-in", work_mode="OFFICE", client_request_id=rid())
    clock.advance(hours=48)
    report = api_client.get(f"{M}/reports/missed-checkouts", headers=MGR).json()
    assert report["total"] == 1 and report["threshold_hours"] == 12
    assert api_client.get(f"{A}/status", headers=hdr()).json()["state"] == "WORKING"


def test_report_splits_overnight_at_local_midnight_and_breaks_down_modes(api_client, clock):
    # 2026-11-09 18:00 UTC is 23:30 in Colombo; two hours crosses local midnight.
    clock.value = datetime(2026, 11, 9, 18, 0, tzinfo=UTC)
    work(api_client, clock, user=7, hours=2, mode="REMOTE")
    work(api_client, clock, user=8, hours=1, mode="OFFICE")
    params = {"date_from": "2026-11-09", "date_to": "2026-11-09"}
    first = api_client.get(f"{M}/reports/summary", params=params, headers=MGR).json()
    assert first["totals"]["gross_seconds"] == 1800
    assert [m["work_mode"] for m in first["by_work_mode"]] == ["REMOTE"]
    params = {"date_from": "2026-11-09", "date_to": "2026-11-10"}
    both = api_client.get(f"{M}/reports/summary", params=params, headers=MGR).json()
    assert both["totals"]["gross_seconds"] == 3 * 3600
    assert {d["date"]: d["gross_seconds"] for d in both["by_day"]} == {"2026-11-09": 1800, "2026-11-10": 9000}
    assert both["employee_total"] == 2


def test_csv_and_xlsx_match_the_report_and_neutralize_formulas(api_client, clock, db):
    claims = {"atwork": {"role": "R", "client_id": None, "client_ids": None, "permissions": list(EMPLOYEE)}}
    from jose import jwt

    from tests.conftest import ISSUER

    token = issue_token(7, module_roles=claims)
    payload = jwt.get_unverified_claims(token)
    payload["full_name"] = "=HYPERLINK(1)"
    import os

    h = bearer(jwt.encode({**payload, "iss": ISSUER}, os.environ["PLATFORM_JWT_SECRET"], algorithm="HS256"))
    post(api_client, f"{A}/check-in", h, work_mode="OFFICE", client_request_id=rid())
    clock.advance(hours=3)
    post(api_client, f"{A}/check-out", h, client_request_id=rid())
    params = {"report": "employee_summary", "date_from": "2026-11-09", "date_to": "2026-11-09"}
    csv_out = api_client.get(f"{M}/reports/export", params={**params, "format": "csv"}, headers=MGR)
    assert csv_out.status_code == 200 and "attachment" in csv_out.headers["content-disposition"]
    lines = csv_out.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Employee,") and lines[1].startswith(
        "'=HYPERLINK(1),7,1,3.0,0.0,3.0,Employee Summary Report,2026-11-09,2026-11-09,"
    )
    xlsx = api_client.get(f"{M}/reports/export", params={**params, "format": "xlsx"}, headers=MGR)
    rows = list(load_workbook(io.BytesIO(xlsx.content)).active.iter_rows(values_only=True))
    assert rows[1] == ("'=HYPERLINK(1)", 7, 1, 3, 0, 3)
    assert db.scalars(select(AttendanceEvent).where(AttendanceEvent.action == "REPORT_EXPORTED")).first() is not None


def test_settings_validate_apply_and_detect_conflicts(api_client, clock):
    current = api_client.get(f"{M}/settings", headers=MGR).json()
    assert current["business_time_zone"] == "Asia/Colombo" and current["version"] == 0
    body = {**current, "enabled_work_modes": ["OFFICE"], "missed_checkout_hours": 4}
    assert (
        api_client.put(f"{M}/settings", json={**body, "business_time_zone": "Mars/Base"}, headers=MGR).json()["code"]
        == "INVALID_TIME_ZONE"
    )
    assert api_client.put(f"{M}/settings", json={**body, "enabled_work_modes": []}, headers=MGR).status_code == 422
    saved = api_client.put(f"{M}/settings", json=body, headers=MGR).json()
    assert saved["version"] == 1
    assert api_client.put(f"{M}/settings", json=body, headers=MGR).json()["code"] == "SETTINGS_CONFLICT"
    denied = post(api_client, f"{A}/check-in", work_mode="REMOTE", client_request_id=rid())
    assert denied.status_code == 422 and denied.json()["code"] == "WORK_MODE_DISABLED"
    assert api_client.get(f"{A}/policy", headers=hdr()).json()["enabled_work_modes"] == ["OFFICE"]
    audit = api_client.get(f"{M}/audit", params={"action": "SETTINGS_UPDATED"}, headers=MGR).json()
    assert audit["total"] == 1 and audit["items"][0]["before_state"]["missed_checkout_hours"] == 12


def test_audit_events_remain_append_only(api_client, clock, db):
    sid = work(api_client, clock)
    r = amend(api_client, sid, work_mode="REMOTE").json()
    post(api_client, f"{M}/corrections/{r['id']}/approve", MGR)
    event = db.scalars(select(AttendanceEvent).where(AttendanceEvent.action == "SESSION_CORRECTED")).one()
    event.action = "TAMPERED"
    with pytest.raises(ValueError):
        db.commit()
