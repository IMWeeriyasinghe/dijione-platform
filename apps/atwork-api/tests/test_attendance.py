from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.routes.attendance import get_clock
from app.main import app
from app.models.attendance import AttendanceBreak, AttendanceEvent, AttendanceSession
from tests.conftest import bearer, issue_token

BASE = "/api/atwork/attendance"
READ = "atwork.attendance.read_own"
RECORD = "atwork.attendance.record_own"


def role(*permissions):
    return {"atwork": {"role": "R", "client_id": None, "client_ids": None, "permissions": list(permissions)}}


def headers(user_id=7, permissions=(READ, RECORD)):
    return bearer(issue_token(user_id, module_roles=role(*permissions)))


class FakeClock:
    def __init__(self):
        self.value = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)

    def __call__(self):
        return self.value

    def advance(self, **kwargs):
        self.value += timedelta(**kwargs)


@pytest.fixture()
def clock():
    fake = FakeClock()
    app.dependency_overrides[get_clock] = lambda: fake
    return fake


counter = iter(range(10_000_000))


def rid():
    return f"request-{next(counter)}"


class Api:
    def __init__(self, client, user_id=7):
        self.client = client
        self.h = headers(user_id)

    def post(self, path, **body):
        body.setdefault("client_request_id", rid())
        return self.client.post(f"{BASE}/{path}", json=body, headers=self.h)

    def get(self, path, **params):
        return self.client.get(f"{BASE}/{path}", params=params, headers=self.h)

    def check_in(self, mode="OFFICE", **kw):
        return self.post("check-in", work_mode=mode, **kw)


@pytest.fixture()
def api(api_client, clock):
    return Api(api_client)


def code(resp):
    return resp.json()["code"]


def test_check_in_and_check_out(api, clock):
    assert api.get("status").json()["state"] == "NOT_CHECKED_IN"
    body = api.check_in("REMOTE").json()
    assert body["replayed"] is False
    assert body["state"] == "WORKING"
    assert body["session"]["work_mode"] == "REMOTE"
    assert datetime.fromisoformat(body["session"]["check_in_at"]) == clock.value
    clock.advance(hours=8)
    assert api.get("status").json()["session"]["totals"]["net_seconds"] == 28800
    out = api.post("check-out").json()
    assert out["state"] == "NOT_CHECKED_IN"
    assert out["session"]["status"] == "COMPLETED"
    assert out["session"]["totals"] == {"gross_seconds": 28800, "break_seconds": 0, "net_seconds": 28800}
    assert api.get("status").json()["session"] is None


def test_client_cannot_supply_identity_or_time(api, clock):
    resp = api.check_in(platform_user_id=99, check_in_at="2020-01-01T00:00:00Z")
    assert resp.status_code == 200
    assert datetime.fromisoformat(resp.json()["session"]["check_in_at"]) == clock.value


def test_invalid_work_mode_and_request_id(api):
    assert api.check_in("MOON").status_code == 422
    assert api.check_in(client_request_id="x").status_code == 422


def test_duplicate_check_in_rejected(api):
    api.check_in()
    resp = api.check_in()
    assert resp.status_code == 409
    assert code(resp) == "ALREADY_CHECKED_IN"


def test_idempotent_check_in_replay_and_conflict(api, db):
    key = rid()
    first = api.check_in(client_request_id=key).json()
    replay = api.check_in(client_request_id=key).json()
    assert replay["replayed"] is True
    assert replay["session"]["id"] == first["session"]["id"]
    assert code(api.check_in("REMOTE", client_request_id=key)) == "IDEMPOTENCY_CONFLICT"
    assert len(db.scalars(select(AttendanceSession)).all()) == 1
    assert len(db.scalars(select(AttendanceEvent)).all()) == 1


def test_idempotent_replay_of_every_action(api, clock, db):
    api.check_in()
    start, end, out = rid(), rid(), rid()
    api.post("breaks/start", client_request_id=start)
    assert api.post("breaks/start", client_request_id=start).json()["replayed"] is True
    clock.advance(minutes=5)
    api.post("breaks/end", client_request_id=end)
    assert api.post("breaks/end", client_request_id=end).json()["replayed"] is True
    clock.advance(minutes=5)
    api.post("check-out", client_request_id=out)
    replay = api.post("check-out", client_request_id=out).json()
    assert replay["replayed"] is True
    assert replay["session"]["status"] == "COMPLETED"
    assert api.post("breaks/start", client_request_id=start).json()["replayed"] is True
    assert len(db.scalars(select(AttendanceBreak)).all()) == 1
    assert len(db.scalars(select(AttendanceEvent)).all()) == 4


def _parallel(fn, count=12):
    with ThreadPoolExecutor(count) as pool:
        return list(pool.map(fn, range(count)))


def test_concurrent_check_ins_create_one_session(api_client, db):
    api = Api(api_client)
    responses = _parallel(lambda _: api.check_in())
    assert sorted(r.status_code for r in responses) == [200] + [409] * 11
    assert {code(r) for r in responses if r.status_code == 409} == {"ALREADY_CHECKED_IN"}
    assert len(db.scalars(select(AttendanceSession)).all()) == 1
    assert len(db.scalars(select(AttendanceEvent)).all()) == 1


def test_concurrent_same_key_check_ins_are_one_action(api_client, db):
    api = Api(api_client)
    key = rid()
    responses = _parallel(lambda _: api.check_in(client_request_id=key))
    assert {r.status_code for r in responses} == {200}
    assert len({r.json()["session"]["id"] for r in responses}) == 1
    assert sum(not r.json()["replayed"] for r in responses) == 1
    assert len(db.scalars(select(AttendanceSession)).all()) == 1


def test_concurrent_same_key_break_and_check_out_are_one_action(api_client, db):
    api = Api(api_client)
    api.check_in()
    start, end, out = rid(), rid(), rid()
    for path, key in (("breaks/start", start), ("breaks/end", end), ("check-out", out)):
        responses = _parallel(lambda _, p=path, k=key: api.post(p, client_request_id=k))
        assert {r.status_code for r in responses} == {200}, path
        assert sum(not r.json()["replayed"] for r in responses) == 1, path
    assert len(db.scalars(select(AttendanceEvent)).all()) == 4


def test_concurrent_break_starts_and_check_outs(api_client, db):
    api = Api(api_client)
    api.check_in()
    breaks = _parallel(lambda _: api.post("breaks/start"))
    assert sorted(r.status_code for r in breaks) == [200] + [409] * 11
    assert len(db.scalars(select(AttendanceBreak)).all()) == 1
    api.post("breaks/end")
    outs = _parallel(lambda _: api.post("check-out"))
    assert sorted(r.status_code for r in outs) == [200] + [409] * 11
    assert {code(r) for r in outs if r.status_code == 409} == {"NOT_CHECKED_IN"}


def test_multiple_sessions_same_day(api, clock):
    for _ in range(3):
        api.check_in()
        clock.advance(hours=1)
        api.post("check-out")
        clock.advance(minutes=30)
    today = api.get("today").json()
    assert today["session_count"] == 3
    assert today["totals"]["net_seconds"] == 10800


def test_break_flow_and_net_time(api, clock):
    api.check_in()
    clock.advance(hours=2)
    assert api.post("breaks/start").json()["state"] == "ON_BREAK"
    clock.advance(minutes=30)
    assert api.post("breaks/end").json()["state"] == "WORKING"
    clock.advance(hours=2)
    api.post("breaks/start")
    clock.advance(minutes=15)
    api.post("breaks/end")
    clock.advance(minutes=15)
    totals = api.post("check-out").json()["session"]["totals"]
    assert totals == {"gross_seconds": 18000, "break_seconds": 2700, "net_seconds": 15300}


def test_invalid_transitions(api):
    assert code(api.post("check-out")) == "NOT_CHECKED_IN"
    assert code(api.post("breaks/start")) == "NOT_CHECKED_IN"
    assert code(api.post("breaks/end")) == "NOT_CHECKED_IN"
    api.check_in()
    assert code(api.post("breaks/end")) == "NO_ACTIVE_BREAK"
    api.post("breaks/start")
    resp = api.post("breaks/start")
    assert resp.status_code == 409
    assert code(resp) == "BREAK_ALREADY_ACTIVE"
    assert "already on a break" in resp.json()["detail"]


def test_check_out_with_open_break_rejected_and_nothing_changes(api, db):
    api.check_in()
    api.post("breaks/start")
    assert code(api.post("check-out")) == "BREAK_STILL_OPEN"
    assert api.get("status").json()["state"] == "ON_BREAK"
    assert len(db.scalars(select(AttendanceEvent)).all()) == 2


def test_long_session_can_check_out_and_is_never_auto_closed(api, clock):
    api.check_in()
    clock.advance(hours=72)
    assert api.get("status").json()["state"] == "WORKING"
    assert api.post("check-out").json()["session"]["totals"]["gross_seconds"] == 259200


def test_clock_behind_latest_record_is_rejected_not_adjusted(api, clock):
    api.check_in()
    clock.advance(hours=1)
    api.post("check-out")
    clock.advance(minutes=-5)
    assert code(api.check_in()) == "TIMELINE_CONFLICT"


def test_cross_midnight_today_and_history(api, clock):
    clock.value = datetime(2026, 11, 9, 17, 0, tzinfo=UTC)  # 22:30 Colombo
    api.check_in()
    clock.advance(hours=4)  # 02:30 next day
    session = api.post("check-out").json()["session"]
    today = api.get("today").json()
    assert today["date"] == "2026-11-10"
    assert today["totals"]["net_seconds"] == 9000
    assert today["session_count"] == 1
    history = api.get("history", date_from="2026-11-09", date_to="2026-11-10").json()
    assert history["total"] == 1
    assert history["sessions"][0]["id"] == session["id"]
    assert [(d["date"], d["net_seconds"]) for d in history["daily_totals"]] == [("2026-11-09", 5400), ("2026-11-10", 9000)]
    only_first = api.get("history", date_from="2026-11-09", date_to="2026-11-09").json()
    assert [(d["date"], d["net_seconds"]) for d in only_first["daily_totals"]] == [("2026-11-09", 5400)]


def test_history_pagination_and_validation(api, clock):
    for _ in range(3):
        api.check_in()
        clock.advance(minutes=10)
        api.post("check-out")
    page = api.get("history", limit=2, offset=2).json()
    assert page["total"] == 3
    assert len(page["sessions"]) == 1
    assert code(api.get("history", date_from="2026-11-10", date_to="2026-11-09")) == "INVALID_DATE_RANGE"
    assert code(api.get("history", date_from="2024-01-01", date_to="2026-11-09")) == "INVALID_DATE_RANGE"


def test_no_absence_records_for_empty_days(api):
    body = api.get("history", date_from="2026-11-01", date_to="2026-11-09").json()
    assert body["daily_totals"] == []


def test_ownership_isolation(api_client, clock):
    alice, bob = Api(api_client, 1), Api(api_client, 2)
    session_id = alice.check_in().json()["session"]["id"]
    assert bob.get("status").json()["session"] is None
    assert bob.get("today").json()["session_count"] == 0
    assert bob.get("history").json()["total"] == 0
    resp = bob.get(f"sessions/{session_id}")
    assert resp.status_code == 404
    assert code(resp) == "SESSION_NOT_FOUND"
    assert alice.get(f"sessions/{session_id}").status_code == 200
    assert code(bob.post("check-out")) == "NOT_CHECKED_IN"
    assert bob.check_in().status_code == 200


def test_same_request_id_is_scoped_per_employee(api_client, clock):
    key = rid()
    first = Api(api_client, 1).check_in(client_request_id=key).json()
    second = Api(api_client, 2).check_in(client_request_id=key).json()
    assert second["replayed"] is False
    assert first["session"]["id"] != second["session"]["id"]


READ_ROUTES = ["status", "today", "history", "sessions/some-id"]
WRITE_ROUTES = ["check-in", "breaks/start", "breaks/end", "check-out"]
BODY = {"client_request_id": "request-abc", "work_mode": "OFFICE"}


def test_unauthenticated_access_is_rejected(api_client):
    for path in READ_ROUTES:
        assert api_client.get(f"{BASE}/{path}").status_code == 401
        assert api_client.get(f"{BASE}/{path}", headers=bearer("not-a-jwt")).status_code == 401
    for path in WRITE_ROUTES:
        assert api_client.post(f"{BASE}/{path}", json=BODY).status_code == 401


def test_permissions_are_enforced_separately(api_client):
    none = bearer(issue_token(7))
    read_only = headers(permissions=(READ,))
    record_only = headers(permissions=(RECORD,))
    for path in READ_ROUTES:
        assert api_client.get(f"{BASE}/{path}", headers=none).status_code == 403
        assert api_client.get(f"{BASE}/{path}", headers=record_only).status_code == 403
    for path in WRITE_ROUTES:
        assert api_client.post(f"{BASE}/{path}", json=BODY, headers=none).status_code == 403
        assert api_client.post(f"{BASE}/{path}", json=BODY, headers=read_only).status_code == 403


def test_audit_events(api, clock, db):
    session_id = api.check_in(client_request_id="audit-check-in").json()["session"]["id"]
    api.post("breaks/start")
    clock.advance(minutes=1)
    api.post("breaks/end")
    clock.advance(minutes=1)
    api.post("check-out")
    api.post("check-out")  # rejected: writes nothing
    events = db.scalars(select(AttendanceEvent).order_by(AttendanceEvent.occurred_at, AttendanceEvent.action.desc())).all()
    assert sorted(e.action for e in events) == ["BREAK_END", "BREAK_START", "CHECK_IN", "CHECK_OUT"]
    assert all(e.actor_user_id == 7 and e.subject_user_id == 7 and e.session_id == session_id for e in events)
    by_action = {e.action: e for e in events}
    assert by_action["CHECK_IN"].before_state is None
    assert by_action["CHECK_IN"].request_id == "audit-check-in"
    assert by_action["CHECK_OUT"].before_state["status"] == "OPEN"
    assert by_action["CHECK_OUT"].after_state["status"] == "COMPLETED"
    assert by_action["BREAK_END"].before_state["ended_at"] is None


def test_audit_events_are_append_only(api, db):
    api.check_in()
    event = db.scalars(select(AttendanceEvent)).one()
    event.action = "TAMPERED"
    with pytest.raises(ValueError):
        db.flush()
    db.rollback()
    db.delete(db.scalars(select(AttendanceEvent)).one())
    with pytest.raises(ValueError):
        db.flush()
    db.rollback()


def _session(user=7, status="OPEN", key="k1", check_out=None):
    now = datetime(2026, 11, 9, tzinfo=UTC)
    return AttendanceSession(
        platform_user_id=user,
        work_mode="OFFICE",
        status=status,
        check_in_at=now,
        check_out_at=check_out,
        time_zone="Asia/Colombo",
        check_in_request_id=key,
        created_by_user_id=user,
        updated_by_user_id=user,
    )


def test_database_allows_one_open_session_per_employee(db):
    db.add(_session(key="a"))
    db.commit()
    db.add(_session(user=8, key="b"))
    db.commit()
    db.add(_session(key="c"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_rejects_inconsistent_status(db):
    db.add(_session(status="COMPLETED"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(_session(check_out=datetime(2026, 11, 8, tzinfo=UTC), status="COMPLETED"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_allows_one_open_break_per_session(db):
    session = _session()
    db.add(session)
    db.commit()
    now = datetime(2026, 11, 9, tzinfo=UTC)
    db.add(AttendanceBreak(session_id=session.id, started_at=now, start_request_id="b1"))
    db.commit()
    db.add(AttendanceBreak(session_id=session.id, started_at=now, start_request_id="b2"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_rejects_break_without_session(db):
    db.add(AttendanceBreak(session_id="missing", started_at=datetime(2026, 11, 9, tzinfo=UTC), start_request_id="b1"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_management_access_is_unchanged(api_client):
    url = "/api/atwork/management/access"
    assert api_client.get(url, headers=headers()).status_code == 403
    assert api_client.get(url, headers=headers(permissions=("atwork.management.access",))).status_code == 200
