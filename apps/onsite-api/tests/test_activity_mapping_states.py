"""Activity across mapping states (v0.8): every recorded event is VERIFIED,
UNMAPPED or CONFLICT for its OWN site-local day; totals reconcile; unverified
events never carry a person; first/last/single use the complete day.

Mock data at dev-site (Asia/Colombo):
  2026-10-13: 101 @08:30, 102 @08:35, 0107 @08:37:00, 0107 @08:37:20, 999 @08:39, 101 @17:30   (6)
  2026-10-14: 103 @08:45, 105 @08:47, 101 @08:48, TEST-AZURE-001 @09:45                         (4)

Mappings used here (synthetic): 101 -> 1 only from 2026-10-14 (partly verified),
0107 -> 1 always, 102 -> 2 AND 102 -> 4 overlapping (a conflict, which the
service never allows but the read path must survive)."""

import io

import pytest
from openpyxl import load_workbook

from tests.conftest import headers_for, make_mapping
from tests.identity_helpers import ready

DAY1, DAY2 = "2026-10-13", "2026-10-14"
RANGE = f"date_from={DAY1}&date_to={DAY2}"
ACT = f"/api/onsite/activity?site_id=dev-site&{RANGE}"


def _get(api_client, path, role="ONSITE_VIEWER"):
    resp = api_client.get(path, headers=headers_for(role))
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def states(api_client, db, directory, audit_calls):
    ready(api_client)
    make_mapping(db, code="101", bamboohr_id="1", valid_from=DAY2)
    make_mapping(db, code="0107", bamboohr_id="1", valid_from="2020-01-01")
    # Overlapping periods (closed + open) — what MAPPING_CONFLICT defends against.
    make_mapping(db, code="102", bamboohr_id="2", valid_from="2020-01-01", valid_to="2026-12-31")
    make_mapping(db, code="102", bamboohr_id="4", valid_from="2026-10-01")
    return api_client


def test_states_reconcile_and_filter(states):
    expected = {"all": 10, "verified": 3, "unverified": 7, "conflict": 1}
    for mapping, total in expected.items():
        body = _get(states, f"{ACT}&mapping={mapping}&page_size=50")
        assert body["total"] == total == len(body["items"]), mapping
        assert body["mapping"] == mapping
        # The summary is the same selection without the mapping filter: identical on every tab.
        assert body["summary"] == {"recorded": 10, "verified": 3, "conflict": 1, "unmapped": 6, "unverified": 7}
    s = _get(states, f"{ACT}&mapping=all")["summary"]
    assert s["recorded"] == s["verified"] + s["unmapped"] + s["conflict"]


def test_each_event_is_classified_for_its_own_day(states):
    items = _get(states, f"{ACT}&mapping=all&page_size=50")["items"]
    by = {(i["emp_code"], i["local_date"], i["local_time"][11:19]): i for i in items}
    assert by[("101", DAY1, "08:30:00")]["mapping_state"] == "UNMAPPED"  # before the mapping's valid_from
    assert by[("101", DAY2, "08:48:00")]["mapping_state"] == "VERIFIED"  # partly verified ID
    assert by[("101", DAY2, "08:48:00")]["bamboohr_id"] == "1"
    assert by[("102", DAY1, "08:35:00")]["mapping_state"] == "CONFLICT"
    assert by[("999", DAY1, "08:39:00")]["mapping_state"] == "UNMAPPED"


def test_unverified_events_never_carry_a_person(states):
    items = _get(states, f"{ACT}&mapping=unverified&page_size=50")["items"]
    assert items
    for i in items:
        assert i["employee_name"] is None and i["bamboohr_id"] is None and i["employee_number"] is None
        assert i["department"] is None and i["has_photo"] is False
        assert i["identity_class"] == ("AMBIGUOUS" if i["mapping_state"] == "CONFLICT" else "UNMATCHED")
        assert i["emp_code"] and i["terminal"] and i["punch_state_raw"] is not None


def test_conflict_is_never_attributed_nor_counted_as_verified(states):
    verified = _get(states, f"{ACT}&mapping=verified&page_size=50")["items"]
    assert "102" not in {i["emp_code"] for i in verified}
    conflict = _get(states, f"{ACT}&mapping=conflict")["items"]
    assert [(i["emp_code"], i["mapping_state"], i["employee_name"]) for i in conflict] == [("102", "CONFLICT", None)]


def test_omitting_mapping_keeps_the_verified_attributed_selection(states):
    body = _get(states, ACT + "&page_size=50")
    assert "summary" not in body and "mapping" not in body
    assert {i["mapping_state"] for i in body["items"]} == {"VERIFIED"}


def test_whole_day_sequence_merges_a_persons_ids(api_client, db, directory, audit_calls):
    ready(api_client)
    make_mapping(db, code="101", bamboohr_id="1", valid_from="2020-01-01")
    make_mapping(db, code="0107", bamboohr_id="1", valid_from="2020-01-01")
    day = f"/api/onsite/activity?site_id=dev-site&date_from={DAY1}&date_to={DAY1}&mapping=all&sort=time&page_size=50"
    seq = [(i["emp_code"], i["punch_sequence"], i["punch_position"], i["punches_in_day"])
           for i in _get(api_client, day)["items"] if i["bamboohr_id"] == "1"]
    assert seq == [("101", "FIRST", 1, 4), ("0107", "INTERMEDIATE", 2, 4), ("0107", "INTERMEDIATE", 3, 4),
                   ("101", "LAST", 4, 4)]
    # Classified on the complete day even when the page shows one event (hour filter, page size 1).
    only = _get(api_client, day + "&hour=17&page_size=1")["items"]
    assert [(i["punch_sequence"], i["punches_in_day"]) for i in only] == [("LAST", 4)]
    single = [i for i in _get(api_client, day)["items"] if i["emp_code"] == "999"]
    assert [(i["punch_sequence"], i["mapping_state"]) for i in single] == [("SINGLE", "UNMAPPED")]


def test_raw_id_filter_search_and_terminal(states):
    by_code = _get(states, f"{ACT}&mapping=all&emp_code=101")
    assert by_code["total"] == 3 and by_code["summary"] == {
        "recorded": 3, "verified": 1, "conflict": 0, "unmapped": 2, "unverified": 2}
    # A name / BHR ID search can only match verified events.
    by_name = _get(states, f"{ACT}&mapping=all&q=A&page_size=50")
    assert by_name["total"] == 3 and {i["mapping_state"] for i in by_name["items"]} == {"VERIFIED"}
    assert _get(states, f"{ACT}&mapping=unverified&q=A")["total"] == 0
    assert _get(states, f"{ACT}&mapping=all&terminal=No-Such-Door")["total"] == 0


def test_paging_and_sort_over_all_states(states):
    first = _get(states, f"{ACT}&mapping=all&sort=time&page=1&page_size=4")
    second = _get(states, f"{ACT}&mapping=all&sort=time&page=2&page_size=4")
    assert first["total"] == second["total"] == 10
    times = [i["local_time"] for i in first["items"] + second["items"]]
    assert len(times) == 8 and times == sorted(times)  # oldest first, no row repeated across pages
    assert len({i["event_id"] if "event_id" in i else (i["emp_code"], i["local_time"])
                for i in first["items"] + second["items"]}) == 8


def test_permissions_and_site_isolation(states):
    viewer = _get(states, f"{ACT}&mapping=all", role="ONSITE_VIEWER")
    assert viewer["total"] == 10 and viewer["can_investigate_identity"] is False
    assert _get(states, f"{ACT}&mapping=all", role="ONSITE_ADMIN")["can_investigate_identity"] is True
    assert states.get(f"{ACT}&mapping=all").status_code == 401
    assert states.get(f"/api/onsite/activity?site_id=syd-site&{RANGE}&mapping=all",
                      headers=headers_for("ONSITE_VIEWER")).status_code == 404  # not enabled
    assert states.get(f"{ACT}&mapping=everything", headers=headers_for("ONSITE_VIEWER")).status_code == 422


def test_overview_charts_and_activity_reconcile(states):
    k = _get(states, f"/api/onsite/dashboard/overview?site_id=dev-site&{RANGE}")["kpis"]
    assert (k["recorded_events"], k["verified_events"], k["unmapped_events"], k["conflict_events"]) == (10, 3, 6, 1)
    hours = _get(states, f"/api/onsite/dashboard/hourly-activity?site_id=dev-site&{RANGE}")["hours"]
    trend = _get(states, f"/api/onsite/dashboard/activity-trend?site_id=dev-site&days=2&date_to={DAY2}")["days"]
    for key in ("events", "verified_events", "unmapped_events", "conflict_events"):
        assert sum(h[key] for h in hours) == sum(d[key] for d in trend)
    assert sum(h["events"] for h in hours) == k["recorded_events"]
    # Whole-day sequence markers: one first+last or one single per identity-day.
    groups = sum(h["first"][s] + h["single"][s] for h in hours for s in ("verified", "unmapped", "conflict"))
    lasts = sum(h["last"][s] for h in hours for s in ("verified", "unmapped", "conflict"))
    firsts = sum(h["first"][s] for h in hours for s in ("verified", "unmapped", "conflict"))
    # 8 identity-days: 13th = person 1 (0107), raw 101, 102 (conflict), 999; 14th = 103, 105, person 1 (101), TEST-AZURE-001.
    assert firsts == lasts and groups == 8


def test_activity_export_scope_follows_the_filter(states):
    resp = states.get(f"/api/onsite/activity/export?site_id=dev-site&{RANGE}&mapping=all",
                      headers=headers_for("ONSITE_VIEWER"))
    assert resp.status_code == 200, resp.text
    wb = load_workbook(io.BytesIO(resp.content))
    assert "Recorded-Activity" in resp.headers["content-disposition"]
    sheet = wb["Recorded Events"]
    rows = [r for r in sheet.iter_rows(values_only=True)]
    header_at = next(i for i, r in enumerate(rows) if r and r[0] == "Local Date")
    header, data = rows[header_at], [r for r in rows[header_at + 1:] if r and r[0]]
    assert len(data) == 10
    col = {name: i for i, name in enumerate(header)}
    for r in data:
        if r[col["Mapping Status"]] != "Verified":
            assert r[col["Team Member Name"]] is None and r[col["BHR ID"]] is None
    summary = {r[0]: r[1] for r in wb["Summary"].iter_rows(values_only=True) if r and r[0]}
    assert summary["Recorded events (all mapping states, same filters)"] == 10
    assert summary["Mapping-conflict events (never attributed)"] == 1
    # The verified export keeps the employee-attributed workbook.
    verified = states.get(f"/api/onsite/activity/export?site_id=dev-site&{RANGE}&mapping=verified",
                          headers=headers_for("ONSITE_VIEWER"))
    assert verified.status_code == 200
    assert "Attendance Report" in load_workbook(io.BytesIO(verified.content)).sheetnames
