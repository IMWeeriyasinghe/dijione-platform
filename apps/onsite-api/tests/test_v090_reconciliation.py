"""v0.9 daily fingerprint activity, extremes, exports — and the reconciliation
proof that every view and export of the same selection adds up.

Synthetic data only: the mock mirror plus a few extra fingerprints inserted
into the TEST mirror (a tie with the earliest fingerprint, a midnight boundary
and a formula-like raw ID). Mappings (synthetic):
  0107 -> 1 always;  101 -> 1 from DAY2 (partly verified: DAY1 unmapped);
  103 -> 1 from DAY2 (two-ID person on DAY2: 101 + 103);
  105 -> 5 until DAY1, -> 6 from DAY2 (reassigned ID);
  102 -> 2 and 102 -> 4 overlapping (conflict);  999 / 888 / TEST-AZURE-001 unmapped.
"""

import io
from collections import Counter
from datetime import datetime

import pytest
from openpyxl import load_workbook

from tests.conftest import headers_for, make_mapping
from tests.identity_helpers import ready
from tests.test_attendance_reviews import _add_event

DAY1, DAY2 = "2026-10-13", "2026-10-14"
R = f"site_id=dev-site&date_from={DAY1}&date_to={DAY2}"
FORBIDDEN = ("first arrival", "last departure", "check-out", "checkout", "check out", "clock out", "clock-out",
             "exit time", "working hours", "time on site", "occupancy")


def _j(client, path, role="ONSITE_ADMIN"):
    resp = client.get(path, headers=headers_for(role))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _wb(client, path, role="ONSITE_VIEWER"):
    resp = client.get(path, headers=headers_for(role))
    assert resp.status_code == 200, resp.text
    return load_workbook(io.BytesIO(resp.content))


def _table(ws, first_header="Date"):
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    start = next(i for i, r in enumerate(rows) if r and r[0] == first_header and len([c for c in r if c]) >= 5)
    return rows[start], [r for r in rows[start + 1:] if any(v is not None for v in r)]


@pytest.fixture()
def mixed(api_client, db, directory, audit_calls):
    ready(api_client, "dev-site", "syd-site")
    make_mapping(db, code="0107", bamboohr_id="1", valid_from="2020-01-01")
    make_mapping(db, code="101", bamboohr_id="1", valid_from=DAY2)
    make_mapping(db, code="103", bamboohr_id="1", valid_from=DAY2)
    make_mapping(db, code="105", bamboohr_id="5", valid_from="2020-01-01", valid_to=DAY1)
    make_mapping(db, code="105", bamboohr_id="6", valid_from=DAY2)
    make_mapping(db, code="102", bamboohr_id="2", valid_from="2020-01-01", valid_to="2026-12-31")
    make_mapping(db, code="102", bamboohr_id="4", valid_from="2026-10-01")
    make_mapping(db, site_id="syd-site", code="110", bamboohr_id="10", valid_from="2020-01-01")
    _add_event(db, code="888", utc=datetime(2026, 10, 13, 3, 0), n=101)  # ties the earliest (08:30 local)
    _add_event(db, code="999", utc=datetime(2026, 10, 13, 18, 29, 30), n=102)  # 23:59:30 DAY1
    _add_event(db, code="999", utc=datetime(2026, 10, 13, 18, 30, 10), n=103)  # 00:00:10 DAY2
    return api_client


# --- daily rows ---------------------------------------------------------------------


def test_daily_rows_for_every_identity(mixed):
    body = _j(mixed, f"/api/onsite/activity/daily?{R}&page_size=200", "ONSITE_VIEWER")
    rows = {(r["local_date"], r["identity_key"]): r for r in body["items"]}
    p1 = rows[(DAY1, "P:1")]  # 0107 x2 on DAY1 (101 still unmapped that day)
    assert p1["zk_emp_codes"] == ["0107"] and p1["punch_count"] == 2 and p1["mapping_state"] == "VERIFIED"
    assert p1["recorded_span_minutes"] == 0 and p1["single"] is False
    assert rows[(DAY1, "C:101")]["mapping_state"] == "UNMAPPED"
    assert rows[(DAY1, "C:101")]["recorded_span_minutes"] == 540
    assert rows[(DAY1, "C:101")]["employee_name"] is None and rows[(DAY1, "C:101")]["bamboohr_id"] is None
    p1d2 = rows[(DAY2, "P:1")]  # two IDs merged
    assert p1d2["zk_emp_codes"] == ["101", "103"] and p1d2["punch_count"] == 2
    assert p1d2["first_fingerprint_local"][11:16] == "08:45" and p1d2["last_fingerprint_local"][11:16] == "08:48"
    assert (DAY1, "P:5") not in rows and (DAY2, "P:5") not in rows  # 105 records only on DAY2 (owner: 6)
    assert rows[(DAY2, "P:6")]["zk_emp_codes"] == ["105"]  # reassigned ID: the DAY2 owner
    conflict = rows[(DAY1, "C:102")]
    assert conflict["mapping_state"] == "CONFLICT" and conflict["bamboohr_id"] is None and conflict["single"]
    assert conflict["recorded_span_minutes"] is None  # unavailable, never 0
    # Midnight boundary: each fingerprint on its own site-local day.
    assert rows[(DAY1, "C:999")]["punch_count"] == 2 and rows[(DAY2, "C:999")]["punch_count"] == 1
    assert body["summary"]["identity_days"] == len(body["items"])


def test_daily_filters_and_paging_after_aggregation(mixed):
    q = f"/api/onsite/activity/daily?{R}"
    assert {r["mapping_state"] for r in _j(mixed, q + "&mapping=unverified&page_size=200")["items"]} \
        == {"UNMAPPED", "CONFLICT"}
    assert [r["identity_key"] for r in _j(mixed, q + "&mapping=conflict")["items"]] == ["C:102"]
    exact = _j(mixed, q + "&emp_code=101&page_size=200")["items"]
    assert {(r["local_date"], r["identity_key"]) for r in exact} == {(DAY1, "C:101"), (DAY2, "P:1")}
    assert {r["identity_key"] for r in _j(mixed, q + "&q=A&page_size=200")["items"]} == {"P:1"}  # names: verified only
    page1 = _j(mixed, q + "&page_size=3&sort=identity")
    page2 = _j(mixed, q + "&page_size=3&page=2&sort=identity")
    assert page1["total"] == page2["total"] and len(page1["items"]) == 3
    assert not {r["identity_key"] + r["local_date"] for r in page1["items"]} & \
        {r["identity_key"] + r["local_date"] for r in page2["items"]}
    # The summary ignores the mapping filter: identical on every tab.
    assert _j(mixed, q + "&mapping=verified")["summary"] == _j(mixed, q + "&mapping=all")["summary"]


def test_daily_dst_site(mixed):
    rows = _j(mixed, "/api/onsite/activity/daily?site_id=syd-site&date_from=2026-10-14&date_to=2026-10-15")["items"]
    r = next(x for x in rows if x["identity_key"] == "P:10")
    assert r["first_fingerprint_local"] == "2026-10-14T09:00:00+11:00" and r["recorded_span_minutes"] == 480
    assert r["time_zone"] == "Australia/Sydney"


def test_extremes_with_ties_over_all_states(mixed):
    ov = _j(mixed, f"/api/onsite/dashboard/overview?site_id=dev-site&date={DAY1}", "ONSITE_VIEWER")
    ex = ov["extremes"]
    assert ex["earliest"]["tied"] == 2 and ex["earliest"]["local_time"][11:19] == "08:30:00"
    assert {e["zk_emp_code"] for e in ex["earliest"]["entries"]} == {"101", "888"}
    assert all(e["employee_name"] is None for e in ex["earliest"]["entries"])  # both unverified that day
    assert ex["latest"]["entries"][0]["zk_emp_code"] == "999" and ex["latest"]["local_time"][11:19] == "23:59:30"
    ranged = _j(mixed, f"/api/onsite/dashboard/overview?site_id=dev-site&date_from={DAY1}&date_to={DAY2}")
    assert ranged["extremes"] is None  # single day only
    events = _j(mixed, f"/api/onsite/activity?site_id=dev-site&date_from={DAY1}&date_to={DAY1}&mapping=all"
                       f"&sort=time&page_size=200")["items"]
    assert events[0]["local_time"] == ex["earliest"]["local_time"] and events[-1]["local_time"] == \
        ex["latest"]["local_time"]


def test_event_items_carry_whole_day_bounds(mixed):
    items = _j(mixed, f"/api/onsite/activity?site_id=dev-site&date_from={DAY2}&date_to={DAY2}&mapping=all"
                      f"&emp_code=103")["items"]
    assert items[0]["day_first_local"][11:16] == "08:45" and items[0]["day_last_local"][11:16] == "08:48"
    assert items[0]["day_span_minutes"] == 3 and items[0]["punches_in_day"] == 2


# --- reconciliation ------------------------------------------------------------------


def test_reconciliation_across_views_and_exports(mixed):
    daily = _j(mixed, f"/api/onsite/activity/daily?{R}&page_size=200")
    act = _j(mixed, f"/api/onsite/activity?{R}&mapping=all&page_size=200")
    s, a = daily["summary"], act["summary"]
    assert (s["verified_punches"], s["unmapped_punches"], s["conflict_punches"]) == \
        (a["verified"], a["unmapped"], a["conflict"])
    assert s["punches"] == a["recorded"] == act["total"] == sum(r["punch_count"] for r in daily["items"])

    # Identity-days == hourly first + single (each identity-day has exactly one first-or-single).
    first_single = 0
    for day in (DAY1, DAY2):
        hours = _j(mixed, f"/api/onsite/dashboard/hourly-activity?site_id=dev-site&date={day}")["hours"]
        first_single += sum(sum(h["first"].values()) + sum(h["single"].values()) for h in hours)
    assert first_single == s["identity_days"] == len(daily["items"])

    hours = _j(mixed, f"/api/onsite/dashboard/hourly-activity?{R}")["hours"]
    trend = _j(mixed, f"/api/onsite/dashboard/activity-trend?site_id=dev-site&days=2&date_to={DAY2}")["days"]
    ov = _j(mixed, f"/api/onsite/dashboard/overview?{R}")
    for key in ("verified_events", "unmapped_events", "conflict_events"):
        assert sum(h[key] for h in hours) == sum(d[key] for d in trend) == ov["kpis"][key]
    assert ov["kpis"]["recorded_events"] == s["punches"]
    assert ov["operational"]["total_punches"] == s["punches"]
    assert ov["operational"]["unmapped_punches"] == s["unmapped_punches"] + s["conflict_punches"]

    # Verified daily rows == Today's verified rows (first, last, count, span) per person-day.
    for day in (DAY1, DAY2):
        today = {r["bamboohr_id"]: r for r in _j(mixed, f"/api/onsite/today?site_id=dev-site&date={day}"
                                                         f"&page_size=200")["items"]}
        ver = {r["bamboohr_id"]: r for r in daily["items"] if r["local_date"] == day and r["mapping_state"] ==
               "VERIFIED"}
        assert set(today) == set(ver)
        for bid, t in today.items():
            v = ver[bid]
            assert (t["first_activity_local"], t["latest_activity_local"], t["punch_count"],
                    t["recorded_span_minutes"]) == (v["first_fingerprint_local"], v["last_fingerprint_local"],
                                                     v["punch_count"], v["recorded_span_minutes"])

    # Daily export == daily API; Recorded Activity export == /activity.
    wb = _wb(mixed, f"/api/onsite/activity/daily/export?{R}&detail=both")
    header, data = _table(wb["Daily Summary"])
    assert len(data) == len(daily["items"])
    assert sum(r[header.index("Punches")] for r in data) == s["punches"]
    _ph, punches = _table(wb["Punch Detail"], "Local Date")
    assert len(punches) == s["punches"]
    rec = _wb(mixed, f"/api/onsite/activity/export?{R}&mapping=all")
    _rh, rec_rows = _table(rec["Recorded Events"], "Local Date")
    assert len(rec_rows) == a["recorded"]

    # Review cases never change any fingerprint count.
    resp = mixed.post("/api/onsite/reviews", json={"site_id": "dev-site", "local_date": DAY1, "zk_emp_code": "999",
                                                   "exception_type": "IDENTITY_ISSUE"}, headers=headers_for())
    assert resp.status_code == 200, resp.text
    assert _j(mixed, f"/api/onsite/activity/daily?{R}&page_size=200")["summary"] == {**s}
    assert _j(mixed, f"/api/onsite/activity?{R}&mapping=all")["summary"] == a


# --- daily export ----------------------------------------------------------------------


def test_daily_export_detail_levels_groups_and_counts(mixed):
    base = f"/api/onsite/activity/daily/export?{R}"
    assert _wb(mixed, base).sheetnames == ["Daily Summary", "Summary"]
    assert _wb(mixed, base + "&detail=detailed").sheetnames == ["Punch Detail", "Case History", "Summary"]
    wb = _wb(mixed, base + "&detail=both")
    assert wb.sheetnames == ["Daily Summary", "Punch Detail", "Case History", "Summary"]
    ws = wb["Daily Summary"]
    labels = [ws.cell(row=r, column=1).value for r in range(1, 40)]
    assert "Recorded evidence" in labels and "Report type" in labels and "Time zone" in labels
    header, rows = _table(ws)
    assert header[:13] == ["Date", "Identity", "BHR ID", "EMP Number", "ZKBioTime ID(s)", "Mapping Status",
                           "First Recorded Fingerprint", "Last Recorded Fingerprint", "Recorded Span (minutes)",
                           "Recorded Span", "Punches", "Single Recorded Fingerprint", "Terminal(s)"]
    assert header[13] == "Classification" and "Estimated Interval (minutes, reviewed estimate)" in header
    single = next(r for r in rows if r[1] == "ZKBioTime ID 102")
    assert single[8] is None and single[9] == "—, Single Recorded Fingerprint" and single[11] == "Yes"
    assert single[3] is None and single[2] is None  # conflict: never attributed
    summary = {r[0]: r[1] for r in wb["Summary"].iter_rows(values_only=True) if r[0]}
    assert "— Administrative review (cases, not fingerprints) —" in summary
    assert summary["Fingerprints in Punch Detail"] == summary["Recorded fingerprints in this export"]


def test_daily_export_single_identity_and_empty(mixed):
    wb = _wb(mixed, f"/api/onsite/activity/daily/export?{R}&bamboohr_id=1")
    _h, rows = _table(wb["Daily Summary"])
    assert {r[2] for r in rows} == {"1"} and len(rows) == 2
    empty = _wb(mixed, "/api/onsite/activity/daily/export?site_id=dev-site&date_from=2026-10-20&date_to=2026-10-20")
    assert empty["Daily Summary"].max_row > 5


def test_daily_export_limits(mixed, monkeypatch):
    from app.services import attendance_export as ex

    monkeypatch.setattr(ex, "MAX_EXPORT_DAY_ROWS", 1)
    resp = mixed.get(f"/api/onsite/activity/daily/export?{R}", headers=headers_for("ONSITE_VIEWER"))
    assert resp.status_code == 413 and "above the limit" in resp.text
    monkeypatch.setattr(ex, "MAX_EXPORT_DAY_ROWS", 20_000)
    monkeypatch.setattr(ex, "MAX_EXPORT_EVENTS", 2)
    resp = mixed.get(f"/api/onsite/activity/daily/export?{R}&detail=both", headers=headers_for("ONSITE_VIEWER"))
    assert resp.status_code == 413


def test_daily_export_formula_injection(mixed, db):
    _add_event(db, code="=HYPERLINK(1)", utc=datetime(2026, 10, 13, 4, 0), n=104)
    wb = _wb(mixed, f"/api/onsite/activity/daily/export?{R}&emp_code==HYPERLINK(1)")
    _h, rows = _table(wb["Daily Summary"])
    assert rows and rows[0][1] == "'ZKBioTime ID =HYPERLINK(1)" or rows[0][4] == "'=HYPERLINK(1)"
    assert all(not (isinstance(c, str) and c.startswith("=")) for r in rows for c in r)


def test_review_columns_in_daily_and_exception_exports(mixed):
    hdr = headers_for()
    case = mixed.post("/api/onsite/reviews", json={"site_id": "dev-site", "local_date": DAY1, "bamboohr_id": "1",
                                                   "exception_type": "DEPARTURE_TIME_QUERY"}, headers=hdr).json()["case"]
    r = mixed.post(f"/api/onsite/reviews/{case['id']}/submit", headers=hdr, json={
        "expected_version": 1, "justification_reason": "FORGOT_TO_RECORD", "declared_departure_local": "17:00",
        "declaration_source": "MANAGER_CONFIRMATION", "explanation": "Manager confirmed the time (synthetic)."})
    assert r.status_code == 200, r.text
    header, rows = _table(_wb(mixed, f"/api/onsite/activity/daily/export?{R}&bamboohr_id=1")["Daily Summary"])
    row = next(x for x in rows if x[0].date().isoformat() == DAY1)
    assert row[header.index("Review Status")] == "Justification submitted"
    assert row[header.index("Estimated Interval (minutes, reviewed estimate)")] == 17 * 60 - (8 * 60 + 37)
    assert row[header.index("Recorded Span (minutes)")] == 0  # observed value unchanged by the estimate
    assert row[header.index("Duration Verified")] == "No"


# --- terminology and authorization -----------------------------------------------------


def _strings(wb):
    for ws in wb.worksheets:
        for r in ws.iter_rows(values_only=True):
            for c in r:
                if isinstance(c, str):
                    yield ws.title, c


def test_no_exit_or_working_hours_wording(mixed):
    paths = [f"/api/onsite/activity/daily/export?{R}&detail=both", f"/api/onsite/activity/export?{R}&mapping=all",
             f"/api/onsite/today/export?site_id=dev-site&date={DAY1}",
             f"/api/onsite/exceptions/export?{R}", f"/api/onsite/dashboard/overview/export?site_id=dev-site&date={DAY1}",
             f"/api/onsite/employees/export?{R}"]
    for path in paths:
        for sheet, text in _strings(_wb(mixed, path)):
            low = text.lower()
            if "not a confirmed" in low or "not working" in low:
                continue  # the fixed disclaimer
            assert not any(f in low for f in FORBIDDEN), (path, sheet, text)
    from app.services import attendance_export as ex
    from app.services import dashboard_service as svc

    for text in [*ex.FLAG_LABEL.values(), *ex.SEQUENCE_LABEL.values(), *svc._FLAG_REASON.values()]:
        assert not any(f in text.lower() for f in FORBIDDEN), text


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/onsite/admin/identity/unmapped?site_id=dev-site"),
    ("GET", "/api/onsite/admin/identity/mappings"),
    ("GET", "/api/onsite/admin/sites"),
    ("GET", "/api/onsite/admin/health"),
    ("POST", "/api/onsite/reviews"),
    ("POST", "/api/onsite/reviews/1/submit"),
    ("POST", "/api/onsite/reviews/1/resolve"),
    ("POST", "/api/onsite/reviews/1/reopen"),
])
def test_on_site_user_cannot_administer(mixed, method, path):
    resp = mixed.request(method, path, headers=headers_for("ONSITE_VIEWER"), json={})
    assert resp.status_code in (403, 422), (path, resp.status_code)
    if resp.status_code == 422:  # body validation runs first; the permission still refuses a valid body
        assert method == "POST"
    body = {"site_id": "dev-site", "local_date": DAY1, "bamboohr_id": "1", "exception_type": "OTHER",
            "expected_version": 1, "justification_reason": "OTHER", "explanation": "x" * 12, "outcome": "JUSTIFIED",
            "decision_note": "x" * 12, "reason": "x" * 12}
    if method == "POST":
        assert mixed.post(path, headers=headers_for("ONSITE_VIEWER"), json=body).status_code == 403


def test_review_summary_counts_not_mixed_with_fingerprints(mixed):
    daily = _j(mixed, f"/api/onsite/activity/daily?{R}&page_size=200")
    states = Counter(r["mapping_state"] for r in daily["items"])
    assert daily["summary"]["verified_identity_days"] == states["VERIFIED"]
    assert "cases" not in " ".join(daily["summary"])
