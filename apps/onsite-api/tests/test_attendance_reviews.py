"""v0.9 attendance exception review lifecycle (synthetic data only).

Mock data at dev-site (Asia/Colombo, UTC+05:30):
  2026-10-13: 101 @08:30 + @17:30 (multi), 102 @08:35 (single), 0107 @08:37:00 + 08:37:20, 999 @08:39 (unmapped)
  2026-10-14: 103 @08:45, 105 @08:47, 101 @08:48, TEST-AZURE-001 @09:45
syd-site (Australia/Sydney, DST): 110 on 2026-10-14 @09:00 and @17:00 AEDT.

Fingerprint records and identity mappings are only read by the review
service; extra fingerprints are inserted into the TEST mirror to simulate new
arrivals (never a real source)."""

from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.models.identity import IdentityMapping
from app.models.mirror import AttendanceEvent
from app.models.review import AttendanceReview, AttendanceReviewEvent
from tests.conftest import headers_for, make_mapping
from tests.identity_helpers import ready

DAY1, DAY2 = "2026-10-13", "2026-10-14"
BASE = "/api/onsite/reviews"
ADMIN, USER = "ONSITE_ADMIN", "ONSITE_VIEWER"
EXPL = "Team member confirmed they left via the push-to-exit button (synthetic)."


@pytest.fixture()
def rv(api_client, db, directory, audit_calls):
    ready(api_client, "dev-site", "syd-site")
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2020-01-01")
    make_mapping(db, code="102", bamboohr_id="2", valid_from="2020-01-01")
    make_mapping(db, site_id="syd-site", code="110", bamboohr_id="10", valid_from="2020-01-01")
    return api_client


def _post(client, path, body, role=ADMIN, user_id=1):
    return client.post(path, json=body, headers=headers_for(role, user_id))


def _open(client, *, day=DAY1, bid=None, code=None, kind="SINGLE_RECORDED_FINGERPRINT", site="dev-site", role=ADMIN):
    body = {"site_id": site, "local_date": day, "exception_type": kind}
    body.update({"bamboohr_id": bid} if bid else {"zk_emp_code": code})
    return _post(client, BASE, body, role)


def _submit(client, case, *, version=None, departure=None, source=None, reason="ASSIGNED_OFF_SITE", explanation=EXPL):
    body = {"expected_version": version or case["version"], "justification_reason": reason,
            "explanation": explanation, "declared_departure_local": departure, "declaration_source": source}
    return _post(client, f"{BASE}/{case['id']}/submit", body)


def _resolve(client, case, *, version=None, outcome="NO_FURTHER_ACTION", note="Reviewed with the team lead (synthetic)."):
    return _post(client, f"{BASE}/{case['id']}/resolve",
                 {"expected_version": version or case["version"], "outcome": outcome, "decision_note": note})


def _ok(resp, code=200):
    assert resp.status_code == code, resp.text
    return resp.json()


def _add_event(db, *, code, utc: datetime, n: int, site="dev-site", tz="Asia/Colombo", offset="+05:30"):
    """Synthetic late-arriving fingerprint in the TEST mirror only."""
    from zoneinfo import ZoneInfo

    local = utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(tz))
    db.add(AttendanceEvent(
        event_id=f"{site}:9:{n}", site_id=site, source_epoch=9, source_transaction_id=n, emp_code=code,
        punch_time_local=local.strftime("%Y-%m-%dT%H:%M:%S") + offset, punch_time_utc=utc, time_zone=tz,
        punch_state="255", verify_type=1, terminal_sn="TERM-01", terminal_alias="Main Door",
        captured_at_utc=utc, received_utc=utc, batch_id="SYN", record_hash=f"syn-{n}",
        site_local_date=local.date(), tz_consistent=True, sync_run_id="synthetic"))
    db.commit()


# --- lifecycle --------------------------------------------------------------------


def test_single_fingerprint_resolved_without_declaration(rv):
    case = _ok(_open(rv, bid="2"))["case"]
    assert (case["status"], case["version"], case["identity_key"]) == ("OPEN", 1, "P:2")
    assert case["facts_snapshot"]["punch_count"] == 1 and case["facts_snapshot"]["recorded_span_minutes"] is None
    case = _ok(_submit(rv, case))["case"]
    assert case["status"] == "SUBMITTED" and case["estimated_minutes"] is None and case["estimate_basis"] is None
    body = _ok(_resolve(rv, case))
    case = body["case"]
    assert case["status"] == "RESOLVED" and case["outcome"] == "NO_FURTHER_ACTION"
    assert case["declared_departure_local"] is None and case["duration_verified"] is False
    assert [h["action"] for h in body["history"]] == ["OPEN", "SUBMIT", "RESOLVE"]
    assert case["opened_by_user_id"] == 1 and case["resolved_by_name"] == "Test User"


def test_single_fingerprint_with_justified_estimate(rv):
    case = _ok(_open(rv, bid="2"))["case"]  # 102 @ 08:35 only
    case = _ok(_submit(rv, case, departure="17:05", source="MANAGER_CONFIRMATION", reason="FORGOT_TO_RECORD"))["case"]
    assert case["estimated_minutes"] == 8 * 60 + 30
    assert case["declared_departure_local"].startswith(f"{DAY1}T17:05:00+05:30")
    assert "First recorded fingerprint 08:35" in case["estimate_basis"]
    assert "not a confirmed duration" in case["estimate_basis"]
    # Observed facts are untouched by the estimate.
    assert case["facts_snapshot"]["punch_count"] == 1 and case["facts_snapshot"]["recorded_span_minutes"] is None


def test_multi_fingerprint_recorded_span_and_estimate(rv):
    case = _ok(_open(rv, bid="1", kind="DEPARTURE_TIME_QUERY"))["case"]  # 101 @ 08:30 + 17:30
    assert case["facts_snapshot"]["recorded_span_minutes"] == 540
    case = _ok(_submit(rv, case, departure="18:00", source="TEAM_MEMBER_STATEMENT"))["case"]
    assert case["estimated_minutes"] == 570  # first fingerprint 08:30 -> declared 18:00
    assert case["facts_snapshot"]["recorded_span_minutes"] == 540  # Recorded Span unchanged


@pytest.mark.parametrize("departure,fragment", [
    ("17:00", "earlier than the latest recorded fingerprint"),   # before latest (17:30)
    ("2026-10-14T01:00", "next-day declarations are not supported"),
    ("25:00", "site-local time"),
    ("17:45+05:30", "site-local time"),
])
def test_invalid_declarations_rejected(rv, departure, fragment):
    case = _ok(_open(rv, bid="1"))["case"]
    resp = _submit(rv, case, departure=departure, source="TEAM_MEMBER_STATEMENT")
    assert resp.status_code == 422 and fragment in resp.text, resp.text
    assert _ok(rv.get(f"{BASE}/{case['id']}", headers=headers_for(USER)))["case"]["version"] == 1  # nothing written


def test_single_declaration_must_be_after_first(rv):
    case = _ok(_open(rv, bid="2"))["case"]
    resp = _submit(rv, case, departure="08:35", source="OTHER")
    assert resp.status_code == 422 and "later than the first recorded fingerprint" in resp.text


def test_declaration_requires_source_and_text_lengths(rv):
    case = _ok(_open(rv, bid="1"))["case"]
    assert _submit(rv, case, departure="18:00", source=None).status_code == 422
    assert _submit(rv, case, explanation="too short").status_code == 422
    case = _ok(_submit(rv, case))["case"]
    assert _resolve(rv, case, note="short").status_code == 422
    case = _ok(_resolve(rv, case))["case"]
    assert _post(rv, f"{BASE}/{case['id']}/reopen", {"expected_version": case["version"], "reason": "no"}).status_code \
        == 422


def test_dst_gap_rejected(rv):
    # Australia/Sydney springs forward 2026-10-04 02:00 -> 03:00. Open on 2026-10-14 (valid), then try a gap time.
    case = _ok(_open(rv, bid="10", site="syd-site", day=DAY2))["case"]
    assert _ok(_submit(rv, case, departure="18:00", source="OTHER"))["case"]["estimated_minutes"] == 9 * 60
    from app.services.attendance_review_service import declared_departure

    with pytest.raises(Exception) as err:
        declared_departure("02:30", datetime(2026, 10, 4).date(), "Australia/Sydney")
    assert "does not exist" in str(err.value.detail)
    with pytest.raises(Exception) as err:  # autumn fold: 2026-04-05 02:30 happens twice
        declared_departure("02:30", datetime(2026, 4, 5).date(), "Australia/Sydney")
    assert "occurs twice" in str(err.value.detail)


def test_reopen_then_resubmit(rv):
    case = _ok(_open(rv, bid="2"))["case"]
    case = _ok(_resolve(rv, _ok(_submit(rv, case))["case"]))["case"]
    body = _ok(_post(rv, f"{BASE}/{case['id']}/reopen",
                     {"expected_version": case["version"], "reason": "New statement received from the manager."}))
    case = body["case"]
    assert case["status"] == "REOPENED" and case["outcome"] == "NO_FURTHER_ACTION"  # prior decision visible
    assert case["reopen_reason"].startswith("New statement")
    case = _ok(_submit(rv, case, departure="17:00", source="MANAGER_CONFIRMATION"))["case"]
    assert case["status"] == "SUBMITTED" and case["outcome"] is None
    hist = _ok(rv.get(f"{BASE}/{case['id']}", headers=headers_for(ADMIN)))["history"]
    assert [h["action"] for h in hist] == ["OPEN", "SUBMIT", "RESOLVE", "REOPEN", "SUBMIT"]
    assert hist[2]["new"]["outcome"] == "NO_FURTHER_ACTION"  # history keeps the earlier decision


def test_illegal_transitions_are_409_without_history(rv, db):
    case = _ok(_open(rv, bid="2"))["case"]
    r = _resolve(rv, case)  # OPEN -> resolve
    assert r.status_code == 409 and r.json()["detail"]["allowed_actions"] == ["submit"]
    r = _post(rv, f"{BASE}/{case['id']}/reopen", {"expected_version": 1, "reason": "Should not be allowed here."})
    assert r.status_code == 409
    case = _ok(_resolve(rv, _ok(_submit(rv, case))["case"]))["case"]
    again = _resolve(rv, case)  # repeated resolve on RESOLVED
    assert again.status_code == 409
    assert _submit(rv, case).status_code == 409
    n = db.execute(select(func.count()).select_from(AttendanceReviewEvent)).scalar_one()
    assert n == 3  # OPEN, SUBMIT, RESOLVE — no duplicates


def test_update_while_submitted_is_one_history_row(rv):
    case = _ok(_open(rv, bid="1"))["case"]
    case = _ok(_submit(rv, case))["case"]
    body = _ok(_submit(rv, case, departure="18:00", source="OTHER"))
    assert body["case"]["version"] == 3 and [h["action"] for h in body["history"]] == ["OPEN", "SUBMIT", "UPDATE"]


def test_concurrent_decisions_one_wins(rv, db):
    case = _ok(_submit(rv, _ok(_open(rv, bid="1"))["case"]))["case"]
    # Two administrators edit the same SUBMITTED version: the second never overwrites the first.
    first = _submit(rv, case, explanation="Administrator A: assigned to the client site (synthetic).")
    second = _submit(rv, case, explanation="Administrator B: different account of events (synthetic).")
    assert first.status_code == 200 and second.status_code == 409
    assert "another administrator" in second.text and second.json()["detail"]["current_version"] == 3
    db.expire_all()
    assert db.get(AttendanceReview, case["id"]).explanation.startswith("Administrator A")
    r1 = _resolve(rv, first.json()["case"], outcome="JUSTIFIED")
    r2 = _resolve(rv, first.json()["case"], outcome="NOT_JUSTIFIED")
    assert r1.status_code == 200 and r2.status_code == 409
    db.expire_all()
    assert db.get(AttendanceReview, case["id"]).outcome == "JUSTIFIED"


def test_conditional_update_guards_a_true_race(rv, db):
    """Both requests passed the in-memory checks; the DB-level version guard lets one win."""
    from fastapi import HTTPException

    from app.db.session import SessionLocal
    from app.services import attendance_review_service as svc
    from app.services.identity_resolution import MappingIndex
    from app.services.workforce_directory import DirectorySnapshot

    case_id = _ok(_submit(rv, _ok(_open(rv, bid="1"))["case"]))["case"]["id"]
    s1, s2 = SessionLocal(), SessionLocal()
    try:
        c1, c2 = s1.get(AttendanceReview, case_id), s2.get(AttendanceReview, case_id)
        index = MappingIndex.load(s1, allowed_site_ids=("dev-site",), directory=DirectorySnapshot(False))

        class Actor:
            id, full_name = 9, "Racer"

        svc.resolve(s1, ("dev-site",), c1, "Asia/Colombo", index, actor=Actor, expected_version=2,
                    outcome="JUSTIFIED", decision_note="First decision wins (synthetic).")
        with pytest.raises(HTTPException) as err:
            # c2 still holds version 2 in memory: the conditional UPDATE matches no row.
            svc._transition(s2, c2, action="resolve", expected_version=2, actor=Actor,
                            values={"status": "RESOLVED", "outcome": "NOT_JUSTIFIED"}, facts={}, note=None)
        assert err.value.status_code == 409
    finally:
        s1.close()
        s2.close()
    db.expire_all()
    assert db.get(AttendanceReview, case_id).outcome == "JUSTIFIED"
    assert db.execute(select(func.count()).select_from(AttendanceReviewEvent)
                      .where(AttendanceReviewEvent.review_id == case_id)).scalar_one() == 3


def test_open_is_idempotent(rv, db):
    a = _ok(_open(rv, bid="1"))
    b = _ok(_open(rv, bid="1", kind="OTHER"))
    assert a["created"] is True and b["created"] is False and a["case"]["id"] == b["case"]["id"]
    assert b["case"]["exception_type"] == "SINGLE_RECORDED_FINGERPRINT"  # never overwritten
    assert db.execute(select(func.count()).select_from(AttendanceReview)).scalar_one() == 1
    assert db.execute(select(func.count()).select_from(AttendanceReviewEvent)).scalar_one() == 1


def test_open_requires_fingerprints_and_correct_key(rv):
    assert _open(rv, bid="1", day="2026-10-20").status_code == 422  # nothing recorded
    resp = _open(rv, code="101")  # 101 is verified that day -> must use the team member
    assert resp.status_code == 422 and "open the case for the team member" in resp.text
    assert _post(rv, BASE, {"site_id": "dev-site", "local_date": DAY1, "exception_type": "OTHER",
                            "bamboohr_id": "1", "zk_emp_code": "101"}).status_code == 422
    assert _open(rv, bid="1", site="nope").status_code == 404


def test_unmapped_case_stays_on_raw_id(rv):
    case = _ok(_open(rv, code="999", kind="IDENTITY_ISSUE"))["case"]
    assert case["identity_key"] == "C:999" and case["bamboohr_id"] is None
    assert case["identity_snapshot"]["mapping_state"] == "UNMAPPED"
    detail = _ok(rv.get(f"{BASE}/day?site_id=dev-site&date={DAY1}&zk_emp_code=999", headers=headers_for(USER)))
    assert detail["case"]["id"] == case["id"] and detail["can_manage"] is False
    assert [p["local_time"][11:16] for p in detail["punches"]] == ["08:39"]


# --- staleness and identity ---------------------------------------------------------


def test_stale_after_new_fingerprint_and_estimate_basis(rv, db):
    case = _ok(_submit(rv, _ok(_open(rv, bid="1"))["case"], departure="18:00", source="OTHER"))["case"]
    assert case["stale"] is False
    _add_event(db, code="101", utc=datetime(2026, 10, 13, 13, 0), n=1)  # 18:30 Colombo, after the declaration
    case = _ok(rv.get(f"{BASE}/{case['id']}", headers=headers_for(ADMIN)))["case"]
    assert case["stale"] is True
    assert set(case["reassess_reasons"]) == {"FINGERPRINTS_CHANGED", "ESTIMATE_BASIS_INVALID"}
    assert case["estimated_minutes"] == 570  # never recalculated
    r = _resolve(rv, case)
    assert r.status_code == 409 and "resubmit" in r.text  # no decision on outdated facts
    case = _ok(_submit(rv, case, departure="18:45", source="OTHER"))["case"]
    assert case["stale"] is False and case["estimated_minutes"] == 615


def test_stale_after_resolution_never_auto_modified(rv, db):
    case = _ok(_resolve(rv, _ok(_submit(rv, _ok(_open(rv, bid="2"))["case"]))["case"]))["case"]
    _add_event(db, code="102", utc=datetime(2026, 10, 13, 12, 0), n=2)
    after = _ok(rv.get(f"{BASE}/{case['id']}", headers=headers_for(USER)))["case"]
    assert after["stale"] and after["status"] == "RESOLVED" and after["version"] == case["version"]
    listed = _ok(rv.get(f"{BASE}?site_id=dev-site&date_from={DAY1}&date_to={DAY1}&status=NEEDS_REASSESSMENT",
                        headers=headers_for(USER)))
    assert [c["id"] for c in listed["items"]] == [case["id"]]


def test_mapping_change_flags_reassessment_without_rekeying(rv, db):
    # Unmapped 999 has a case; later 999 is verified for team member 5. The case
    # stays on C:999, is flagged, and its estimate is never moved to the person.
    case = _ok(_submit(rv, _ok(_open(rv, code="999"))["case"], departure="17:00", source="OTHER"))["case"]
    make_mapping(db, code="999", bamboohr_id="5", valid_from="2020-01-01")
    after = _ok(rv.get(f"{BASE}/{case['id']}", headers=headers_for(ADMIN)))["case"]
    assert after["identity_key"] == "C:999" and after["bamboohr_id"] is None
    assert "IDENTITY_CHANGED" in after["reassess_reasons"] and after["identity_changed"]
    assert after["identity_snapshot"]["mapping_state"] == "UNMAPPED"  # original context preserved
    daily = _ok(rv.get(f"/api/onsite/activity/daily?site_id=dev-site&date_from={DAY1}&date_to={DAY1}&page_size=50",
                       headers=headers_for(USER)))
    person = next(r for r in daily["items"] if r["bamboohr_id"] == "5")
    assert person["review"] is None  # no case was moved onto the person
    assert [c["id"] for c in person["earlier_code_cases"]] == [case["id"]]
    assert person["earlier_code_cases"][0]["stale"] is True
    assert db.get(AttendanceReview, case["id"]).estimated_minutes == after["estimated_minutes"]


def test_person_case_flagged_when_mapping_closed(rv, db):
    case = _ok(_open(rv, bid="1"))["case"]
    m = db.execute(select(IdentityMapping).where(IdentityMapping.zk_emp_code == "101")).scalar_one()
    m.valid_to = datetime(2026, 10, 12).date()  # synthetic correction in the TEST db
    db.commit()
    after = _ok(rv.get(f"{BASE}/{case['id']}", headers=headers_for(ADMIN)))
    assert after["case"]["identity_changed"] and after["current_facts"]["punch_count"] == 0
    assert after["case"]["identity_key"] == "P:1"


def test_conflict_case_never_attributed(rv, db):
    make_mapping(db, code="0107", bamboohr_id="7", valid_from="2020-01-01", valid_to="2026-12-31")
    make_mapping(db, code="0107", bamboohr_id="1", valid_from="2026-10-01")
    assert _open(rv, bid="7").status_code == 422  # conflict days are not the person's
    case = _ok(_open(rv, code="0107", kind="IDENTITY_ISSUE"))["case"]
    assert case["identity_snapshot"]["mapping_state"] == "CONFLICT" and case["bamboohr_id"] is None


# --- security -----------------------------------------------------------------------


def test_user_reads_but_cannot_write(rv):
    case = _ok(_open(rv, bid="1"))["case"]
    assert _open(rv, bid="2", role=USER).status_code == 403
    for path, body in [(f"{BASE}/{case['id']}/submit", {"expected_version": 1, "justification_reason": "OTHER",
                                                         "explanation": EXPL}),
                       (f"{BASE}/{case['id']}/resolve", {"expected_version": 1, "outcome": "JUSTIFIED",
                                                          "decision_note": EXPL}),
                       (f"{BASE}/{case['id']}/reopen", {"expected_version": 1, "reason": EXPL})]:
        assert _post(rv, path, body, role=USER).status_code == 403
        assert rv.post(path, json=body).status_code == 401
    listed = _ok(rv.get(f"{BASE}?site_id=dev-site&date_from={DAY1}&date_to={DAY2}", headers=headers_for(USER)))
    assert listed["total"] == 1 and listed["can_manage"] is False
    assert rv.get(f"{BASE}?site_id=dev-site").status_code == 401


def test_kill_switch(rv, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "onsite_review_writes_enabled", False)
    assert _open(rv, bid="1").status_code == 503
    assert rv.get(f"{BASE}?site_id=dev-site", headers=headers_for(USER)).status_code == 200


def test_audit_and_no_attendance_writes(rv, db, audit_calls):
    before = db.execute(select(func.count()).select_from(AttendanceEvent)).scalar_one()
    maps = db.execute(select(func.count()).select_from(IdentityMapping)).scalar_one()
    case = _ok(_open(rv, bid="1"))["case"]
    _ok(_resolve(rv, _ok(_submit(rv, case))["case"]))
    assert [c["action"] for c in audit_calls if c.get("entity_type") == "OnsiteAttendanceReview"] == [
        "ONSITE_REVIEW_OPEN", "ONSITE_REVIEW_SUBMIT", "ONSITE_REVIEW_RESOLVE"]
    assert db.execute(select(func.count()).select_from(AttendanceEvent)).scalar_one() == before
    assert db.execute(select(func.count()).select_from(IdentityMapping)).scalar_one() == maps


def test_exceptions_carry_review_and_filter(rv):
    case = _ok(_open(rv, bid="2"))["case"]
    q = f"/api/onsite/exceptions?site_id=dev-site&date_from={DAY1}&date_to={DAY1}"
    body = _ok(rv.get(q, headers=headers_for(USER)))
    row = next(r for r in body["items"] if r["bamboohr_id"] == "2")
    assert row["review"]["id"] == case["id"] and row["review"]["status"] == "OPEN"
    assert body["can_manage_reviews"] is False
    assert {r["bamboohr_id"] for r in _ok(rv.get(q + "&review_status=OPEN", headers=headers_for(USER)))["items"]} \
        == {"2"}
    assert "2" not in {r["bamboohr_id"] for r in
                       _ok(rv.get(q + "&review_status=not_reviewed", headers=headers_for(USER)))["items"]}
