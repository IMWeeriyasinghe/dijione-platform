"""Excel exports contain the ENTIRE filtered result set: UI filters define the
dataset, pagination never does. Built on a 400-employee dataset so every
view spans several UI pages."""

import dataclasses
import io
from datetime import datetime, timedelta

import pytest
from openpyxl import load_workbook

from app.attendance_source import mock_client
from app.services import attendance_export, mirror_sync_service, workforce_directory
from tests.conftest import enable_site, headers_for, map_directory, run_sync

DAY, OTHER_DAY = "2026-10-13", "2026-10-20"
N, FINANCE = 400, 137  # employees with activity on DAY; Finance subset
V = headers_for("ONSITE_VIEWER")


def _code(i: int) -> str:
    return f"E{i:03d}"


def _dataset():
    base = datetime(2026, 10, 13, 3, 0, 0)  # 08:30 Colombo
    ev = []
    for i in range(N):
        e = mock_client._event(i, "dev-site", 1000, 10_000 + i, _code(i), base + timedelta(seconds=i * 30),
                               mock_client._COLOMBO)
        ev.append(dataclasses.replace(e, terminal_alias="Back Door" if i % 4 == 0 else "Main Door"))
    # outside the selected date / on a site that is not enabled — must never be exported
    for i in range(50):
        ev.append(mock_client._event(1000 + i, "dev-site", 1000, 20_000 + i, _code(i),
                                     datetime(2026, 10, 20, 4, 0, 0) + timedelta(minutes=i), mock_client._COLOMBO))
        ev.append(mock_client._event(2000 + i, "syd-site", 1, 30_000 + i, _code(i),
                                     datetime(2026, 10, 12, 23, 0, 0) + timedelta(minutes=i), mock_client._SYDNEY))
    # E000 has two activities on OTHER_DAY (so SINGLE_PUNCH only on DAY);
    # E001 is hired between DAY and OTHER_DAY (identity differs per day).
    ev.append(mock_client._event(3000, "dev-site", 1000, 40_000, _code(0), datetime(2026, 10, 20, 12, 0, 0),
                                 mock_client._COLOMBO))
    return ev


def _directory():
    out = []
    for i in range(N):
        out.append({"bamboohr_id": str(i), "employee_number": _code(i), "display_name": f"Person {i:03d}",
                    "department": "Finance" if i < FINANCE else "Operations",
                    "employment_status": "Inactive" if i % 10 == 9 else "Active",
                    "hire_date": "2020-01-01", "termination_date": "2026-01-01" if i % 10 == 9 else None,
                    "location": "Sri Lanka", "job_title": "Analyst"})
    out[1]["hire_date"] = "2026-10-15"
    return out


@pytest.fixture()
def big(api_client, db, audit_calls, monkeypatch):
    events = _dataset()
    monkeypatch.setattr(mirror_sync_service, "get_onsite_source", lambda: mock_client.MockOnsiteSource(events))
    snapshot = workforce_directory.DirectorySnapshot(available=True, entries=_directory())
    monkeypatch.setattr(workforce_directory, "load", lambda force=False: snapshot)
    map_directory(snapshot.entries)
    run_sync(api_client)
    enable_site(api_client, "dev-site")  # syd-site stays disabled
    return api_client


def _xlsx_rows(client, url, sheet):
    resp = client.get(url, headers=V)
    assert resp.status_code == 200, resp.text
    ws = load_workbook(io.BytesIO(resp.content))[sheet]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    start = next(i for i, r in enumerate(rows) if len(r) > 1 and r[1] in ("Employee Name", "Local Time", "BHR Employee ID"))
    header = rows[start]
    data = [dict(zip(header, r, strict=False)) for r in rows[start + 1:] if r[1] is not None]
    return data, {r[0]: r[1] for r in rows[4:start] if r[0]}


def _pages(client, url, page_size=50):
    """Walk every UI page; returns (per-page sizes, all items, reported total)."""
    sizes, items, page = [], [], 1
    while True:
        body = client.get(f"{url}&page={page}&page_size={page_size}", headers=V).json()
        sizes.append(len(body["items"]))
        items += body["items"]
        if page * page_size >= body["total"]:
            return sizes, items, body["total"]
        page += 1


def _codes(rows, key=None):
    """ZKBioTime IDs of the export rows (attendance/employees: "ZKBioTime ID(s)"; events: "ZKBioTime ID")."""
    key = key or ("ZKBioTime ID(s)" if rows and "ZKBioTime ID(s)" in rows[0] else "ZKBioTime ID")
    return sorted(r[key] for r in rows)


# --- pagination independence: every view, filtered and unfiltered ------------------


def test_today_exports_all_pages(big):
    sizes, items, total = _pages(big, f"/api/onsite/today?date={DAY}&department=Finance")
    assert (total, sizes) == (FINANCE, [50, 50, 37])
    rows, meta = _xlsx_rows(big, f"/api/onsite/today/export?date={DAY}&department=Finance", "Attendance Report")
    assert len(rows) == FINANCE and _codes(rows) == sorted(i["emp_code"] for i in items)
    assert meta["Department"] == "Finance" and meta["Date"] == DAY


def test_today_no_optional_filters_exports_whole_day_only(big):
    sizes, _, total = _pages(big, f"/api/onsite/today?date={DAY}")
    assert total == N and len(sizes) == 8
    rows, _ = _xlsx_rows(big, f"/api/onsite/today/export?date={DAY}", "Attendance Report")
    assert len(rows) == N and {str(r["Date"])[:10] for r in rows} == {DAY}  # no other dates / sites


def test_activity_exports_all_pages(big):
    q = f"date_from={DAY}&date_to={DAY}&department=Finance"
    sizes, items, total = _pages(big, f"/api/onsite/activity?{q}")
    assert (total, sizes) == (FINANCE, [50, 50, 37])
    events, _ = _xlsx_rows(big, f"/api/onsite/activity/export?{q}", "Event Detail")
    days, _ = _xlsx_rows(big, f"/api/onsite/activity/export?{q}", "Attendance Report")
    assert len(events) == total and len(days) == FINANCE
    assert _codes(events) == sorted(i["emp_code"] for i in items)


def test_activity_no_optional_filters_respects_range_and_site(big):
    q = f"date_from={DAY}&date_to={OTHER_DAY}"
    _, _, total = _pages(big, f"/api/onsite/activity?{q}")
    assert total == N + 51  # dev-site only: 400 on DAY + 51 on OTHER_DAY, no syd-site rows
    events, _ = _xlsx_rows(big, f"/api/onsite/activity/export?{q}", "Event Detail")
    assert len(events) == total


def test_employees_exports_all_pages(big):
    q = f"date_from={DAY}&date_to={DAY}&department=Finance&activity=with_activity"
    sizes, items, total = _pages(big, f"/api/onsite/employees?{q}")
    assert (total, sizes) == (FINANCE, [50, 50, 37])
    rows, meta = _xlsx_rows(big, f"/api/onsite/employees/export?{q}", "Employees")
    assert len(rows) == FINANCE and _codes(rows) == sorted(i["emp_code"] for i in items)
    assert meta["Activity"] == "Activity recorded"


def test_exceptions_exports_all_pages(big):
    q = f"date_from={DAY}&date_to={DAY}&department=Finance&flag=SINGLE_PUNCH"
    sizes, items, total = _pages(big, f"/api/onsite/exceptions?{q}", page_size=25)
    assert total == FINANCE and len(sizes) == 6
    rows, meta = _xlsx_rows(big, f"/api/onsite/exceptions/export?{q}", "Exception Report")
    assert len(rows) == FINANCE and _codes(rows) == sorted(i["emp_code"] for i in items)
    assert meta["Review / exception type"] == "Single activity"


def test_page_params_cannot_change_the_export(big):
    base = f"/api/onsite/today/export?date={DAY}&department=Finance"
    a, _ = _xlsx_rows(big, base, "Attendance Report")
    b, _ = _xlsx_rows(big, f"{base}&page=3&page_size=10", "Attendance Report")  # ignored by the export
    assert len(a) == len(b) == FINANCE


# --- filter correctness on every view (export rows == every UI page combined) --------

FILTER_CASES = [
    ("today", f"date={DAY}", "Attendance Report", "emp_code=E007"),
    ("today", f"date={DAY}", "Attendance Report", "q=person%2001"),
    ("today", f"date={DAY}", "Attendance Report", "identity_class=MATCHED_INACTIVE"),
    ("today", f"date={DAY}", "Attendance Report", "review=SINGLE_PUNCH&department=Operations"),
    ("activity", f"date_from={DAY}&date_to={OTHER_DAY}", "Event Detail", "terminal=Back%20Door"),
    ("activity", f"date_from={DAY}&date_to={OTHER_DAY}", "Event Detail", "identity_class=MATCHED_INACTIVE"),
    ("activity", f"date_from={DAY}&date_to={OTHER_DAY}", "Event Detail", "flag=SINGLE_PUNCH"),
    ("activity", f"date_from={DAY}&date_to={OTHER_DAY}", "Event Detail", "q=person%2001&department=Finance"),
    ("activity", f"date_from={DAY}&date_to={OTHER_DAY}", "Event Detail", "emp_code=E003"),
    ("activity", f"date_from={DAY}&date_to={OTHER_DAY}", "Event Detail", "flag=SINGLE_PUNCH&emp_code=E000"),
    ("activity", f"date_from={DAY}&date_to={OTHER_DAY}", "Event Detail", "identity_class=MATCHED_BEFORE_HIRE"),
    ("activity", f"date_from={DAY}&date_to={OTHER_DAY}", "Event Detail", "identity_class=MATCHED_ACTIVE&emp_code=E001"),
    ("employees", f"date_from={DAY}&date_to={DAY}", "Employees", "employment_status=Inactive"),
    ("employees", f"date_from={DAY}&date_to={DAY}", "Employees", "identity_class=MATCHED_INACTIVE&department=Finance"),
    ("employees", f"date_from={DAY}&date_to={DAY}", "Employees", "q=person%2012&activity=with_activity"),
    ("exceptions", f"date_from={DAY}&date_to={OTHER_DAY}", "Exception Report", "flag=INACTIVE_EMPLOYEE_ACTIVITY"),
    ("exceptions", f"date_from={DAY}&date_to={OTHER_DAY}", "Exception Report", "emp_code=E019"),
    ("exceptions", f"date_from={DAY}&date_to={OTHER_DAY}", "Exception Report",
     "identity_class=MATCHED_INACTIVE&department=Operations"),
]


@pytest.mark.parametrize(("view", "dates", "sheet", "filters"), FILTER_CASES)
def test_export_matches_ui_for_filter(big, view, dates, sheet, filters):
    sizes, items, total = _pages(big, f"/api/onsite/{view}?{dates}&{filters}", page_size=10)
    rows, _ = _xlsx_rows(big, f"/api/onsite/{view}/export?{dates}&{filters}", sheet)
    assert total > 0 and len(rows) == total, (view, filters, total, len(rows))
    assert _codes(rows) == sorted(i["emp_code"] for i in items)


# --- size limit: full export within the limit, explicit error above it ----------------


def test_limit_exports_fully_at_threshold_and_errors_above(big, monkeypatch):
    url = f"/api/onsite/today/export?date={DAY}&department=Finance"
    monkeypatch.setattr(attendance_export, "MAX_EXPORT_DAY_ROWS", FINANCE)
    rows, _ = _xlsx_rows(big, url, "Attendance Report")
    assert len(rows) == FINANCE  # exactly at the limit: complete, not truncated
    monkeypatch.setattr(attendance_export, "MAX_EXPORT_DAY_ROWS", FINANCE - 1)
    resp = big.get(url, headers=V)
    assert resp.status_code == 413
    assert "137 rows" in resp.json()["detail"] and "Narrow the date range" in resp.json()["detail"]
    monkeypatch.setattr(attendance_export, "MAX_EXPORT_DAY_ROWS", 20_000)
    monkeypatch.setattr(attendance_export, "MAX_EXPORT_EVENTS", FINANCE - 1)
    resp = big.get(f"/api/onsite/activity/export?date_from={DAY}&date_to={DAY}&department=Finance", headers=V)
    assert resp.status_code == 413


def test_employees_limit_errors_instead_of_truncating(big, monkeypatch):
    monkeypatch.setattr(attendance_export, "MAX_EXPORT_DAY_ROWS", 100)
    resp = big.get(f"/api/onsite/employees/export?date_from={DAY}&date_to={DAY}&activity=with_activity", headers=V)
    assert resp.status_code == 413
