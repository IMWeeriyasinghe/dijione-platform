"""Stage 2: mapping lifecycle safety (S1-S5) and same-day reassignment.

Mock data at dev-site: code 101 punches on 2026-10-13 (x2) and 2026-10-14 (x1).
"""

from datetime import date

import pytest

from app.core.constants import MappingStatus
from app.models.identity import IdentityEvent, IdentityMapping, IdentityRejection
from app.services import identity_admin_service as ia
from app.services.identity_resolution import MappingIndex
from app.services.workforce_directory import DirectorySnapshot
from tests.conftest import DIRECTORY, headers_for
from tests.identity_helpers import BASE, EVIDENCE, create, ready

D = date.fromisoformat
DIR = DirectorySnapshot(available=True, entries=DIRECTORY)


def _owner(db, code, day, site="dev-site"):
    r = MappingIndex.load(db, allowed_site_ids=(site,), directory=DIR).resolve(site, code, D(day))
    return r.bamboohr_id if r.identified else r.mapping_status.value


def _reassign(api_client, code, d, new_bid, handling=None, ack=True):
    body = {"site_id": "dev-site", "effective_from": d, "reason": "code reissued by IT to a new joiner",
            "new": {"bamboohr_id": new_bid, "evidence": EVIDENCE}, "same_day_handling": handling}
    resp = api_client.post(f"{BASE}/codes/{code}/reassign", json=body, headers=headers_for())
    if ack and resp.status_code == 422 and resp.json()["detail"].get("error") == "WARNINGS_NOT_ACKNOWLEDGED":
        body["new"]["acknowledged_warnings"] = resp.json()["detail"]["unacknowledged"]
        resp = api_client.post(f"{BASE}/codes/{code}/reassign", json=body, headers=headers_for())
    return resp


def test_s1_close_preserves_attribution_inside_period(api_client, db, directory, audit_calls):
    ready(api_client)
    mid = create(api_client, code="101", bid="1", valid_from="2026-10-01").json()["id"]
    resp = api_client.post(f"{BASE}/mappings/{mid}/close", headers=headers_for(),
                           json={"valid_to": "2026-10-13", "reason": "employee left on 13 October"})
    assert resp.status_code == 200 and resp.json()["status"] == "VERIFIED"
    db.expire_all()
    assert _owner(db, "101", "2026-10-13") == "1"  # inside: kept
    assert _owner(db, "101", "2026-10-14") == "UNMAPPED"  # after: unmapped
    again = api_client.post(f"{BASE}/mappings/{mid}/close", headers=headers_for(),
                            json={"valid_to": "2026-10-12", "reason": "trying to shorten again"})
    assert again.status_code == 409 and again.json()["detail"]["error"] == "ALREADY_CLOSED"
    assert [e.action for e in db.query(IdentityEvent).filter_by(entity_id=mid).order_by(IdentityEvent.id)] == [
        "CREATED", "CLOSED"]


def test_s2_correct_withdraws_only_the_superseded_period(api_client, db, directory, audit_calls):
    ready(api_client)
    a = create(api_client, code="101", bid="1", valid_from="2026-01-01", valid_to="2026-10-13").json()["id"]
    create(api_client, code="101", bid="2", valid_from="2026-10-14")
    resp = api_client.post(f"{BASE}/mappings/{a}/correct", headers=headers_for(),
                           json={"reason": "HR evidence shows a different owner", "replacement": {
                               "bamboohr_id": "7", "valid_from": "2026-10-13", "valid_to": "2026-10-13",
                               "evidence": EVIDENCE, "acknowledged_warnings": [
                                   "PRIOR_UNMAPPED_ACTIVITY", "ADJACENT_MAPPING", "CODE_REUSED"]}})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["superseded"]["status"] == "SUPERSEDED" and out["superseded"]["superseded_by_id"] == out["replacement"]["id"]
    db.expire_all()
    assert _owner(db, "101", "2026-10-12") == "UNMAPPED"  # old period no longer attributed
    assert _owner(db, "101", "2026-10-13") == "7"  # replacement
    assert _owner(db, "101", "2026-10-14") == "2"  # untouched neighbour
    assert db.get(IdentityMapping, a).status == "SUPERSEDED"  # never deleted
    superseded = api_client.post(f"{BASE}/mappings/{a}/close", headers=headers_for(),
                                 json={"valid_to": "2026-10-01", "reason": "cannot touch superseded"})
    assert superseded.status_code == 409


def test_s3_reassign_without_activity_on_day_is_d_minus_1_d(api_client, db, directory, audit_calls):
    ready(api_client)
    old = create(api_client, code="101", bid="1", valid_from="2026-01-01").json()["id"]
    resp = _reassign(api_client, "101", "2026-10-20", "2")  # no punches on 2026-10-20
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["previous"]["valid_to"] == "2026-10-19" and body["new"]["valid_from"] == "2026-10-20"
    assert body["same_day_handling"] is None
    assert db.query(IdentityEvent).filter_by(entity_id=old, action="REASSIGNED").count() == 1


def test_same_day_reassignment_is_never_split_automatically(api_client, db, directory, audit_calls):
    ready(api_client)
    create(api_client, code="101", bid="1", valid_from="2026-01-01")
    resp = _reassign(api_client, "101", "2026-10-14", "2")  # 101 punched on 2026-10-14
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "REASSIGNMENT_DAY_HAS_ACTIVITY" and detail["events_on_day"] == 1
    db.expire_all()
    assert _owner(db, "101", "2026-10-14") == "1"  # nothing changed


@pytest.mark.parametrize("handling,on_day,prev_end,new_start", [
    ("leave_unmapped", "UNMAPPED", "2026-10-13", "2026-10-15"),
    ("attribute_to_new", "2", "2026-10-13", "2026-10-14"),
    ("attribute_to_previous", "1", "2026-10-14", "2026-10-15"),
])
def test_same_day_handlings(api_client, db, directory, audit_calls, handling, on_day, prev_end, new_start):
    ready(api_client)
    create(api_client, code="101", bid="1", valid_from="2026-01-01")
    resp = _reassign(api_client, "101", "2026-10-14", "2", handling=handling)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["previous"]["valid_to"], body["new"]["valid_from"]) == (prev_end, new_start)
    db.expire_all()
    assert _owner(db, "101", "2026-10-13") == "1"
    assert _owner(db, "101", "2026-10-14") == on_day
    assert _owner(db, "101", "2026-10-16") == "2"
    if handling == "leave_unmapped":
        days = api_client.get(f"{BASE}/conflicts?site_id=dev-site", headers=headers_for()).json()[
            "ambiguous_reassignment_days"]
        assert days == [{"site_id": "dev-site", "zk_emp_code": "101", "local_date": "2026-10-14", "events": 1,
                         "flag": "AMBIGUOUS_REASSIGNMENT_DAY"}]


def test_rejection_blocks_only_its_period_and_can_be_withdrawn(api_client, db, directory, audit_calls):
    ready(api_client)
    rej = api_client.post(f"{BASE}/rejections", headers=headers_for(), json={
        "site_id": "dev-site", "zk_emp_code": "105", "bamboohr_id": "6", "reason": "HR: not this person in 2026",
        "applies_from": "2026-01-01"}).json()
    blocked = create(api_client, code="105", bid="6", valid_from="2026-10-01")
    assert blocked.status_code == 409 and blocked.json()["detail"]["error"] == "REJECTED_ASSOCIATION"
    # A different historical period is not blocked by a bounded rejection.
    assert create(api_client, code="105", bid="6", valid_from="2025-01-01", valid_to="2025-12-31").status_code == 201
    w = api_client.post(f"{BASE}/rejections/{rej['id']}/withdraw", headers=headers_for(),
                        json={"reason": "rejection entered for the wrong code"})
    assert w.status_code == 200 and w.json()["status"] == "WITHDRAWN"
    assert create(api_client, code="105", bid="6", valid_from="2026-10-01").status_code == 201
    assert db.query(IdentityRejection).count() == 1  # never deleted
    actions = [c["action"] for c in audit_calls if c.get("entity_type") == "OnsiteIdentityRejection"]
    assert actions == ["onsite.identity.rejection.created", "onsite.identity.rejection.withdrawn"]


def test_cannot_reject_a_currently_verified_pair(api_client, db, directory, audit_calls):
    ready(api_client)
    create(api_client, code="101", bid="1", valid_from="2026-01-01")
    resp = api_client.post(f"{BASE}/rejections", headers=headers_for(), json={
        "site_id": "dev-site", "zk_emp_code": "101", "bamboohr_id": "1", "reason": "conflicting instruction"})
    assert resp.status_code == 409


def test_s4_failed_write_leaves_no_partial_state(db, directory, monkeypatch):
    actor = ia.Actor(user_id=1, allowed_site_ids=("dev-site",))
    ia.create_mapping(db, actor, DIR, ia.MappingInput("dev-site", "101", "1", D("2026-01-01"), None, EVIDENCE,
                                                       ("NO_ATTENDANCE_FOR_CODE",)))

    def boom(*a, **k):
        raise RuntimeError("history write failed")

    monkeypatch.setattr(ia.IdentityRepository, "add_event", boom)
    with pytest.raises(RuntimeError):
        ia.reassign_code(db, actor, DIR, site_id="dev-site", zk_emp_code="101", effective_from=D("2026-03-01"),
                         reason="code reissued by IT", new_bamboohr_id="2", new_valid_to=None, new_evidence=EVIDENCE,
                         acknowledged_warnings=["NO_ATTENDANCE_FOR_CODE", "CODE_REUSED", "ADJACENT_MAPPING"])
    db.expire_all()
    rows = db.query(IdentityMapping).all()
    assert len(rows) == 1 and rows[0].valid_to is None  # previous owner untouched, no new row


def test_s5_history_keeps_before_and_after(api_client, db, directory, audit_calls):
    ready(api_client)
    mid = create(api_client, code="101", bid="1", valid_from="2026-01-01").json()["id"]
    api_client.post(f"{BASE}/mappings/{mid}/close", headers=headers_for(),
                    json={"valid_to": "2026-06-30", "reason": "ownership ended 30 June"})
    ev = db.query(IdentityEvent).filter_by(entity_id=mid, action="CLOSED").one()
    assert '"valid_to": null' in ev.previous_json and '"valid_to": "2026-06-30"' in ev.new_json


def test_reassign_requires_a_single_current_owner(api_client, db, directory, audit_calls):
    ready(api_client)
    resp = _reassign(api_client, "101", "2026-10-20", "2")
    assert resp.status_code == 409 and resp.json()["detail"]["error"] == "NO_CURRENT_OWNER"


def test_mapping_status_resolution_after_lifecycle(db):
    assert MappingStatus.UNMAPPED.value == "UNMAPPED"
