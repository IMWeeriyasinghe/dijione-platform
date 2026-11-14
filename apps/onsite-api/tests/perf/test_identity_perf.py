"""Synthetic performance + regression run for verified identity resolution.

Opt-in (slow): ``RUN_PERF=1 pytest tests/perf -s``. Runs on SQLite by default
or on PostgreSQL when DATABASE_URL points at one. SYNTHETIC DATA ONLY.

Dataset (one site, Asia/Colombo, 92 days ending 2026-11-13):
- 420 ZKBioTime IDs, ~58k punches (heavier per day than the real Colombo feed);
- 360 BambooHR employees; IDs P0000-P0299 -> employees 0-299;
- P0300-P0349 are SECOND IDs of employees 0-49 (multi-ID employees);
- P0350-P0389 are REASSIGNED half-way (employee 300+k, then 330+k... capped);
- P0390-P0419 are never mapped (must never reach viewer records).
"""

from __future__ import annotations

import io
import os
import random
import time
from datetime import UTC, date, datetime, timedelta

import pytest
from openpyxl import load_workbook

from app.models.identity import IdentityMapping
from app.models.mirror import AttendanceEvent, SiteSettings, SourceSite
from app.services import workforce_directory
from tests.conftest import headers_for

pytestmark = pytest.mark.skipif(os.environ.get("RUN_PERF") != "1", reason="set RUN_PERF=1 to run")

SITE = "perf-site"
END = date(2026, 11, 13)
START = END - timedelta(days=91)
MID = START + timedelta(days=46)
N_CODES, N_EMP = 420, 360
TIMINGS: list[tuple[str, float]] = []


def _code(i: int) -> str:
    return f"P{i:04d}"


def _owner(i: int, day: date) -> str | None:
    if i < 300:
        return str(i)
    if i < 350:
        return str(i - 300)  # second ID of employees 0-49
    if i < 390:
        k = i - 350
        return str(300 + k % 30) if day < MID else str(330 + k % 30)
    return None


@pytest.fixture()
def perf(api_client, db, audit_calls, monkeypatch):
    rnd = random.Random(42)
    directory = [{"bamboohr_id": str(e), "employee_number": f"EN{e:04d}", "display_name": f"Synthetic Person {e:03d}",
                  "department": ["Engineering", "Support", "Finance"][e % 3], "job_title": "Engineer",
                  "employment_status": "Inactive" if e % 25 == 24 else "Active", "hire_date": "2020-01-01",
                  "termination_date": "2026-09-30" if e % 25 == 24 else None, "location": "Sri Lanka", "has_photo": False}
                 for e in range(N_EMP)]
    snap = workforce_directory.DirectorySnapshot(available=True, entries=directory)
    monkeypatch.setattr(workforce_directory, "load", lambda force=False: snap)
    db.add(SourceSite(site_id=SITE, display_name="Perf Site", time_zone="Asia/Colombo", is_active=True))
    db.add(SiteSettings(site_id=SITE, enabled=True))
    rows, tx = [], 0
    d = START
    while d <= END:
        weekday = d.weekday() < 5
        for i in range(N_CODES):
            if rnd.random() > (0.75 if weekday else 0.08):
                continue
            for p in range(rnd.choice((1, 2, 2, 3, 4))):
                tx += 1
                local = datetime(d.year, d.month, d.day, 8 + p * 3, rnd.randrange(60), tzinfo=None)
                utc = local - timedelta(hours=5, minutes=30)
                rows.append({"event_id": f"{SITE}:1:{tx}", "site_id": SITE, "source_epoch": 1, "source_transaction_id": tx,
                             "emp_code": _code(i), "punch_time_local": local.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30",
                             "punch_time_utc": utc, "time_zone": "Asia/Colombo", "punch_state": "255", "verify_type": 1,
                             "terminal_sn": f"T{p % 2}", "terminal_alias": ["Main Door", "Back Door"][p % 2],
                             "area_alias": "Ground", "captured_at_utc": utc, "received_utc": utc,
                             "batch_id": "perf", "record_hash": f"h{tx}", "site_local_date": d, "tz_consistent": True,
                             "sync_run_id": "perf", "mirrored_at": datetime.now(UTC)})
        d += timedelta(days=1)
    db.bulk_insert_mappings(AttendanceEvent, rows)
    maps = []
    for i in range(390):
        common = dict(site_id=SITE, zk_emp_code=_code(i), status="VERIFIED", evidence="synthetic perf mapping",
                      verified_by_user_id=1, source="IMPORT")
        if 350 <= i < 390:
            maps.append(IdentityMapping(bamboohr_id=_owner(i, START), valid_from=START - timedelta(days=400),
                                        valid_to=MID - timedelta(days=1), **common))
            maps.append(IdentityMapping(bamboohr_id=_owner(i, MID), valid_from=MID, **common))
        else:
            maps.append(IdentityMapping(bamboohr_id=_owner(i, START), valid_from=START - timedelta(days=400), **common))
    db.add_all(maps)
    db.commit()
    return {"events": len(rows), "client": api_client}


def _timed(client, name, path, role="ONSITE_ADMIN"):
    t = time.perf_counter()
    resp = client.get(path, headers=headers_for(role))
    TIMINGS.append((name, time.perf_counter() - t))
    assert resp.status_code == 200, (name, resp.text[:300])
    return resp


def test_identity_resolution_at_volume(perf):
    c = perf["client"]
    V = "ONSITE_VIEWER"
    rng = f"site_id={SITE}&date_from={START}&date_to={END}"
    unmapped = {_code(i) for i in range(390, N_CODES)}

    one_day = f"/api/onsite/dashboard/overview?site_id={SITE}&date={END - timedelta(days=1)}"
    ov_day = _timed(c, "overview 1 day", one_day, V).json()
    ov = _timed(c, "overview 92 days", f"/api/onsite/dashboard/overview?{rng}").json()
    assert "operational" in ov and ov["operational"]["unmapped_codes"] == 30
    assert ov["kpis"]["employees_with_activity"] <= N_EMP and ov_day["kpis"]["employees_with_activity"] <= N_EMP
    _timed(c, "hourly 92 days", f"/api/onsite/dashboard/hourly-activity?{rng}", V)
    trend = _timed(c, "trend 92 days", f"/api/onsite/dashboard/activity-trend?site_id={SITE}&days=92&date_to={END}", V).json()
    assert max(dd["employees"] for dd in trend["days"]) <= N_EMP

    day = END - timedelta(days=1)
    today = _timed(c, "today (200 rows)", f"/api/onsite/today?site_id={SITE}&date={day}&page_size=200", V).json()
    bids = [r["bamboohr_id"] for r in today["items"]]
    assert len(bids) == len(set(bids)), "an employee with two IDs must be ONE row"
    assert not {cd for r in today["items"] for cd in r["zk_emp_codes"]} & unmapped

    # Pagination: pages are disjoint and add up to the total.
    seen, page = [], 1
    while True:
        body = _timed(c, f"employees 92d p{page}", f"/api/onsite/employees?{rng}&page={page}&page_size=100",
                      V).json()
        seen += [r["bamboohr_id"] for r in body["items"]]
        if page * 100 >= body["total"]:
            break
        page += 1
    assert len(seen) == len(set(seen)) == body["total"] <= N_EMP

    act1 = _timed(c, "activity 92d page 1", f"/api/onsite/activity?{rng}&page=1&page_size=200", V).json()
    act2 = _timed(c, "activity 92d page 2", f"/api/onsite/activity?{rng}&page=2&page_size=200", V).json()
    k1 = {(i["local_time"], i["emp_code"]) for i in act1["items"]}
    k2 = {(i["local_time"], i["emp_code"]) for i in act2["items"]}
    assert not k1 & k2 and act1["total"] == act2["total"] < perf["events"]
    assert not {i["emp_code"] for i in act1["items"] + act2["items"]} & unmapped
    _timed(c, "exceptions 92d", f"/api/onsite/exceptions?{rng}&page_size=200", V)

    # Reassigned ID: each owner sees only their own half.
    a = _timed(c, "detail (reassigned, first owner)", f"/api/onsite/employees/by-id/300?{rng}", V).json()
    b = _timed(c, "detail (reassigned, second owner)", f"/api/onsite/employees/by-id/330?{rng}", V).json()
    assert all(d_["local_date"] < str(MID) for d_ in a["days"] if "P0350" in d_["zk_emp_codes"])
    assert all(d_["local_date"] >= str(MID) for d_ in b["days"] if "P0350" in d_["zk_emp_codes"])
    multi = _timed(c, "detail (two IDs)", f"/api/onsite/employees/by-id/0?{rng}", V).json()
    assert sorted(multi["profile"]["zk_emp_codes"]) == ["P0000", "P0300"]
    # Legacy route fails closed for the reassigned ID over the whole period.
    t = time.perf_counter()
    assert c.get(f"/api/onsite/employees/P0350?{rng}", headers=headers_for(V)).status_code == 404
    TIMINGS.append(("legacy detail (reassigned -> 404)", time.perf_counter() - t))

    week = f"site_id={SITE}&date_from={END - timedelta(days=6)}&date_to={END}"
    x = _timed(c, "export today", f"/api/onsite/today/export?site_id={SITE}&date={day}", V)
    _timed(c, "export activity 7d", f"/api/onsite/activity/export?{week}", V)
    emp_x = _timed(c, "export employees 92d", f"/api/onsite/employees/export?{rng}", V)
    _timed(c, "export exceptions 7d", f"/api/onsite/exceptions/export?{week}", V)
    wb = load_workbook(io.BytesIO(emp_x.content))
    listed = {r[0]: r[1] for r in wb["Summary"].iter_rows(values_only=True) if r[0]}["Team members listed"]
    assert listed == body["total"]
    text = " ".join(str(v) for ws in load_workbook(io.BytesIO(x.content)) for row in ws.iter_rows(values_only=True)
                    for v in row if v is not None)
    assert not any(f" {cd} " in f" {text} " for cd in unmapped)

    _timed(c, "admin unmapped", "/api/onsite/admin/identity/unmapped?page_size=50")
    _timed(c, "admin readiness 30d", f"/api/onsite/admin/identity/readiness?site_id={SITE}&days=30")
    _timed(c, "admin conflicts", f"/api/onsite/admin/identity/conflicts?site_id={SITE}")

    dialect = os.environ.get("DATABASE_URL", "sqlite").split(":")[0]
    print(f"\n--- identity perf ({dialect}): {perf['events']:,} events, {N_CODES} IDs, {N_EMP} employees ---")
    for name, secs in TIMINGS:
        print(f"{name:40s} {secs * 1000:8.0f} ms")
    slow = [(n, s) for n, s in TIMINGS if s > 15]
    assert not slow, slow
