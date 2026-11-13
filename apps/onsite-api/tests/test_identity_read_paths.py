"""Stage 3: verified identity in every viewer read path.

Mock data at dev-site (Asia/Colombo):
  2026-10-13: 101 x2, 102 x1, 0107 x2 (20 s apart), 999 x1
  2026-10-14: 103 x1, 105 x1, 101 x1, TEST-AZURE-001 x1
Directory (synthetic): bamboohr 1 has Employee Number "101", 2 -> "102", 7 -> "0107" ...
"""

import hashlib
import io
import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.models.mirror import AttendanceEvent
from tests.conftest import headers_for, make_mapping
from tests.identity_helpers import BASE, EVIDENCE, create, ready

DAY1, DAY2 = "2026-10-13", "2026-10-14"
V = "ONSITE_VIEWER"
RANGE = f"date_from={DAY1}&date_to={DAY2}"
JSON_VIEWS = [f"/api/onsite/dashboard/overview?date={DAY1}", f"/api/onsite/dashboard/overview?{RANGE}",
              f"/api/onsite/dashboard/hourly-activity?date={DAY1}",
              f"/api/onsite/dashboard/activity-trend?days=2&date_to={DAY2}", "/api/onsite/dashboard/recent-activity",
              f"/api/onsite/today?date={DAY1}", f"/api/onsite/today?date={DAY2}", f"/api/onsite/activity?{RANGE}",
              f"/api/onsite/employees?{RANGE}", f"/api/onsite/exceptions?{RANGE}"]
EXPORTS = [f"/api/onsite/today/export?date={DAY1}", f"/api/onsite/activity/export?{RANGE}",
           f"/api/onsite/employees/export?{RANGE}", f"/api/onsite/exceptions/export?{RANGE}",
           f"/api/onsite/dashboard/overview/export?date={DAY1}"]


def _get(client, path, role=V):
    return client.get(path, headers=headers_for(role))


def _xlsx_text(resp) -> str:
    assert resp.status_code == 200, resp.text
    wb = load_workbook(io.BytesIO(resp.content))
    return "\n".join(" | ".join("" if v is None else str(v) for v in row)
                     for ws in wb for row in ws.iter_rows(values_only=True))


def _items(body):
    return body.get("items", [])


# --- no numeric attribution leaks anywhere ----------------------------------------------


def test_no_mapping_means_no_identity_anywhere(api_client, db, directory, audit_calls):
    """The directory has Employee Numbers equal to every mock code, but nothing
    is verified: no viewer surface may show a person, a code row or a photo."""
    ready(api_client)
    for path in JSON_VIEWS:
        body = _get(api_client, path).json()
        text = json.dumps(body)
        for name in ('"A"', '"B"', '"C"', '"D"', '"E"', '"F"'):
            assert name not in text, (path, name)
        assert _items(body) == [], path
    k = _get(api_client, f"/api/onsite/dashboard/overview?date={DAY1}").json()["kpis"]
    assert (k["employees_with_activity"], k["total_events"]) == (0, 0)
    for code in ("101", "102", "0107", "105"):
        assert _get(api_client, f"/api/onsite/employees/{code}?{RANGE}").status_code == 404
        assert _get(api_client, f"/api/onsite/employees/{code}/photo").status_code == 404
    assert _get(api_client, f"/api/onsite/employees/by-id/1?{RANGE}").status_code == 404
    assert _get(api_client, "/api/onsite/employees/by-id/1/photo").status_code == 404
    assert _get(api_client, f"/api/onsite/today?date={DAY1}&q=A").json()["items"] == []
    for path in EXPORTS:
        text = _xlsx_text(_get(api_client, path))
        assert "No records match the selected filters." in text or "| A |" not in text, path
        for code in (" 101 ", " 0107 ", " 999 "):
            assert f"|{code}|" not in text, (path, code)
    rows = _get(api_client, "/api/onsite/admin/identity-match", "ONSITE_ADMIN").json()["rows"]
    assert all(r["matches"] == [] and r["identity_class"] == "UNMATCHED" for r in rows)


def test_numeric_matching_is_not_reachable_from_read_paths():
    """Static guard: Employee Number indexing is used only for the labelled admin hint."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    users = sorted(str(p.relative_to(app_dir)) for p in app_dir.rglob("*.py")
                   if "by_employee_number" in p.read_text(encoding="utf-8"))
    assert users == ["services/identity_admin_service.py", "services/workforce_directory.py"]
    assert not (app_dir / "services" / "identity_match_service.py").exists()


# --- legacy compatibility layer -------------------------------------------------------------


def test_legacy_vocabulary_is_derived_from_verified_employee(api_client, db, directory, audit_calls):
    ready(api_client)
    make_mapping(db, code="103", bamboohr_id="3", valid_from="2020-01-01")  # bamboohr 3: Inactive
    make_mapping(db, code="999", bamboohr_id="2", valid_from="2020-01-01")  # verified despite no number match
    for path in JSON_VIEWS:
        body = _get(api_client, path).json()
        classes = {i.get("identity_class") for i in _items(body)}
        assert not classes & {"UNMATCHED", "AMBIGUOUS"}, path
    today = {r["emp_code"]: r for r in _get(api_client, f"/api/onsite/today?date={DAY1}").json()["items"]}
    assert today["999"]["employee_name"] == "B" and today["999"]["bamboohr_id"] == "2"
    assert today["999"]["identity_class"] == "MATCHED_ACTIVE" and today["999"]["mapping_status"] == "MAPPED"
    t2 = {r["emp_code"]: r for r in _get(api_client, f"/api/onsite/today?date={DAY2}").json()["items"]}
    assert t2["103"]["identity_class"] == "MATCHED_INACTIVE" and "INACTIVE_EMPLOYEE_ACTIVITY" in t2["103"]["flags"]


def test_legacy_switch_off_removes_code_addressed_routes(api_client, db, directory, audit_calls, monkeypatch):
    from app.core.config import get_settings

    ready(api_client)
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2020-01-01")
    assert _get(api_client, f"/api/onsite/employees/101?{RANGE}").status_code == 200
    monkeypatch.setattr(get_settings(), "onsite_legacy_contract", False)
    assert _get(api_client, f"/api/onsite/employees/101?{RANGE}").status_code == 404
    assert _get(api_client, "/api/onsite/employees/101/photo").status_code == 404
    assert _get(api_client, "/api/onsite/admin/identity-match", "ONSITE_ADMIN").status_code == 404
    detail = _get(api_client, f"/api/onsite/employees/by-id/1?{RANGE}").json()
    assert detail["profile"]["bamboohr_id"] == "1" and detail["summary"]["events"] == 3


# --- distinct identities, never codes -----------------------------------------------------------


def test_two_codes_one_employee_is_one_person_everywhere(api_client, db, directory, audit_calls):
    ready(api_client)
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2020-01-01")
    make_mapping(db, code="0107", bamboohr_id="1", valid_from="2020-01-01")
    k = _get(api_client, f"/api/onsite/dashboard/overview?date={DAY1}").json()["kpis"]
    assert (k["employees_with_activity"], k["total_events"], k["identified_employees"]) == (1, 4, 1)
    hours = _get(api_client, f"/api/onsite/dashboard/hourly-activity?date={DAY1}").json()["hours"]
    assert max(h["employees"] for h in hours) == 1 and sum(h["events"] for h in hours) == 4
    trend = _get(api_client, f"/api/onsite/dashboard/activity-trend?days=2&date_to={DAY2}").json()["days"]
    assert [(d["employees"], d["events"]) for d in trend] == [(1, 4), (1, 1)]
    today = _get(api_client, f"/api/onsite/today?date={DAY1}").json()
    assert today["total"] == 1
    row = today["items"][0]
    assert row["zk_emp_codes"] == ["0107", "101"] and row["punch_count"] == 4 and row["bamboohr_id"] == "1"
    assert "POSSIBLE_DUPLICATE_TAP" in row["flags"] and row["terminal_names"] == ["Main Door"]
    emp = _get(api_client, f"/api/onsite/employees?{RANGE}").json()
    assert emp["total"] == 1 and emp["items"][0]["events"] == 5 and emp["items"][0]["activity_days"] == 2
    detail = _get(api_client, f"/api/onsite/employees/by-id/1?{RANGE}").json()
    assert detail["summary"]["events"] == 5 and sorted(m["zk_emp_code"] for m in detail["mappings"]) == ["0107",
                                                                                                         "101"]
    assert len(detail["events"]) == 5
    legacy = _get(api_client, f"/api/onsite/employees/0107?{RANGE}").json()  # either ID opens the same person
    assert legacy["profile"]["bamboohr_id"] == "1" and legacy["summary"]["events"] == 5
    wb = load_workbook(io.BytesIO(_get(api_client, f"/api/onsite/employees/export?{RANGE}").content))
    summary = {r[0]: r[1] for r in wb["Summary"].iter_rows(values_only=True) if r[0]}
    assert summary["Employees listed"] == 1 and summary["Attendance events"] == 5
    wb = load_workbook(io.BytesIO(_get(api_client, f"/api/onsite/today/export?date={DAY1}").content))
    summary = {r[0]: r[1] for r in wb["Summary"].iter_rows(values_only=True) if r[0]}
    assert summary["Employees with activity"] == 1 and summary["Attendance events"] == 4


# --- effective dates ------------------------------------------------------------------------------


def test_mapping_applies_only_inside_its_period(api_client, db, directory, audit_calls):
    ready(api_client)
    make_mapping(db, code="101", bamboohr_id="1", valid_from=DAY2)  # Tom-style: verified from day 2 only
    assert _get(api_client, f"/api/onsite/today?date={DAY1}").json()["items"] == []
    assert [r["emp_code"] for r in _get(api_client, f"/api/onsite/today?date={DAY2}").json()["items"]] == ["101"]
    act = _get(api_client, f"/api/onsite/activity?{RANGE}").json()
    assert act["total"] == 1 and act["items"][0]["local_date"] == DAY2
    emp = _get(api_client, f"/api/onsite/employees?{RANGE}").json()["items"][0]
    assert (emp["events"], emp["activity_days"]) == (1, 1)


def test_reassigned_code_splits_attendance_between_owners(api_client, db, directory, audit_calls):
    ready(api_client)
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2020-01-01", valid_to=DAY1)
    make_mapping(db, code="101", bamboohr_id="2", valid_from=DAY2)
    d1 = _get(api_client, f"/api/onsite/today?date={DAY1}").json()["items"]
    d2 = _get(api_client, f"/api/onsite/today?date={DAY2}").json()["items"]
    assert [(r["emp_code"], r["bamboohr_id"]) for r in d1] == [("101", "1")]
    assert [(r["emp_code"], r["bamboohr_id"]) for r in d2] == [("101", "2")]
    a = _get(api_client, f"/api/onsite/employees/by-id/1?{RANGE}").json()
    b = _get(api_client, f"/api/onsite/employees/by-id/2?{RANGE}").json()
    assert (a["summary"]["events"], b["summary"]["events"]) == (2, 1)
    assert {e["local_date"] for e in a["events"]} == {DAY1} and {e["local_date"] for e in b["events"]} == {DAY2}
    # Legacy code addressing opens the most recent verified owner in the period.
    assert _get(api_client, f"/api/onsite/employees/101?{RANGE}").json()["profile"]["bamboohr_id"] == "2"
    act = {(i["local_date"], i["bamboohr_id"]) for i in _get(api_client, f"/api/onsite/activity?{RANGE}"
                                                            "&emp_code=101").json()["items"]}
    assert act == {(DAY1, "1"), (DAY2, "2")}


def test_activity_search_by_name_and_bhr_id_not_by_code(api_client, db, directory, audit_calls):
    ready(api_client)
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2020-01-01")
    assert _get(api_client, f"/api/onsite/activity?{RANGE}&q=a").json()["total"] == 3  # name "A"
    assert _get(api_client, f"/api/onsite/today?date={DAY1}&q=999").json()["items"] == []


# --- unmapped visibility split -------------------------------------------------------------------


def test_unmapped_hidden_from_viewers_visible_to_admins(api_client, db, directory, audit_calls):
    ready(api_client)
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2020-01-01")
    viewer = _get(api_client, f"/api/onsite/dashboard/overview?date={DAY1}").json()
    assert "operational" not in viewer and viewer["kpis"]["total_events"] == 2
    admin = _get(api_client, f"/api/onsite/dashboard/overview?date={DAY1}", "ONSITE_ADMIN").json()
    assert admin["operational"] == {"active_codes": 4, "total_punches": 6, "unmapped_codes": 3,
                                    "unmapped_punches": 4}
    unmapped = {r["zk_emp_code"] for r in _get(api_client, f"{BASE}/unmapped?page_size=50", "ONSITE_ADMIN")
                .json()["items"]}
    assert {"999", "102", "0107", "TEST-AZURE-001"} <= unmapped and "101" not in unmapped


# --- raw data untouched --------------------------------------------------------------------------------


def _events_digest(db) -> str:
    rows = db.query(AttendanceEvent).order_by(AttendanceEvent.event_id).all()
    payload = [(e.event_id, e.emp_code, e.site_id, str(e.punch_time_utc), e.record_hash, str(e.site_local_date))
               for e in rows]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def test_identity_operations_never_touch_raw_events(api_client, db, directory, audit_calls):
    ready(api_client)
    before = _events_digest(db)
    mid = create(api_client, code="101", bid="1", valid_from="2026-01-01").json()["id"]
    api_client.post(f"{BASE}/codes/101/reassign", headers=headers_for(), json={
        "site_id": "dev-site", "effective_from": "2026-10-20", "reason": "code reissued by IT",
        "new": {"bamboohr_id": "2", "evidence": EVIDENCE,
                "acknowledged_warnings": ["NO_ATTENDANCE_FOR_CODE", "CODE_REUSED", "ADJACENT_MAPPING",
                                          "PRIOR_UNMAPPED_ACTIVITY"]}})
    api_client.post(f"{BASE}/mappings/{mid}/correct", headers=headers_for(), json={"reason": "wrong person entirely"})
    api_client.post(f"{BASE}/rejections", headers=headers_for(), json={
        "site_id": "dev-site", "zk_emp_code": "999", "bamboohr_id": "1", "reason": "HR: not this person"})
    db.expire_all()
    assert _events_digest(db) == before


@pytest.mark.parametrize("path", EXPORTS)
def test_exports_never_contain_unverified_ids(api_client, db, directory, audit_calls, path):
    ready(api_client)
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2020-01-01")
    text = _xlsx_text(_get(api_client, path))
    for code in ("999", "TEST-AZURE-001", "0107", "105"):
        assert f"| {code} |" not in text and f"| {code}\n" not in text, (path, code)
