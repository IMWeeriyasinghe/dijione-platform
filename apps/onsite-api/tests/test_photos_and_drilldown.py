"""Employee photos (people-api proxy, cached), hour drill-down, paging and
lazy detail loading."""

import threading
import time
from datetime import date, datetime

import httpx
import pytest

from app.models.mirror import AttendanceEvent
from app.services import dashboard_service as svc
from app.services import employee_photos, workforce_directory
from app.services.employee_photos import Photo, PhotoCache
from tests.conftest import DIRECTORY, enable_site, headers_for, run_sync

DAY1, DAY2 = "2026-10-13", "2026-10-14"
PNG = b"\x89PNG\r\n\x1a\n0000"


def _ready(api_client):
    run_sync(api_client)
    enable_site(api_client, "dev-site")


def _get(api_client, path, role="ONSITE_VIEWER"):
    return api_client.get(path, headers=headers_for(role))


@pytest.fixture()
def photo_directory(monkeypatch):
    entries = [dict(e) for e in DIRECTORY]
    for e in entries:
        e["has_photo"] = e.get("employee_number") in ("101", "105")  # 105 is ambiguous in DIRECTORY
    snapshot = workforce_directory.DirectorySnapshot(available=True, entries=entries)
    monkeypatch.setattr(workforce_directory, "load", lambda force=False: snapshot)
    return snapshot


# --- photo cache -------------------------------------------------------------

def test_cache_deduplicates_and_caches_hits_and_misses():
    calls = []

    def fetch(bid):
        calls.append(bid)
        return (Photo(PNG, "image/png"), 60) if bid == "has" else (None, 60)

    cache = PhotoCache(fetch=fetch)
    for _ in range(5):
        assert cache.get("has").content == PNG
        assert cache.get("none") is None
    assert calls == ["has", "none"]  # one upstream call each, then cached (positive and negative)


def test_cache_expires_and_respects_throttle_window(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(employee_photos.time, "monotonic", lambda: now[0])
    calls = []
    cache = PhotoCache(fetch=lambda bid: (calls.append(bid), (None, 30))[1])  # e.g. throttled: Retry-After 30
    cache.get("a")
    now[0] += 29
    cache.get("a")
    now[0] += 2
    cache.get("a")
    assert len(calls) == 2  # no retry inside the throttle window, retried after it


def test_single_flight_and_bounded_concurrency():
    started, active, peak = threading.Event(), [0], [0]
    lock = threading.Lock()

    def slow(bid):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        started.set()
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        return Photo(PNG, "image/png"), 60

    cache = PhotoCache(fetch=slow, max_concurrent=2)
    threads = [threading.Thread(target=cache.get, args=("same",)) for _ in range(8)]
    threads += [threading.Thread(target=cache.get, args=(f"k{i}",)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert cache.upstream_calls == 7  # 1 for "same" (shared) + 6 distinct
    assert peak[0] <= 2


def test_cache_is_bounded():
    cache = PhotoCache(fetch=lambda bid: (Photo(PNG, "image/png"), 60), max_entries=3)
    for i in range(5):
        cache.get(str(i))
    cache.get("0")
    assert cache.upstream_calls == 6  # "0" was evicted (LRU) and fetched again


def test_upstream_status_mapping(monkeypatch):
    class Client:
        def __init__(self, resp):
            self.resp = resp

        def get_photo(self, bid):
            if isinstance(self.resp, Exception):
                raise self.resp
            return self.resp

    cases = [
        (httpx.Response(200, content=PNG, headers={"content-type": "image/png"}), True, employee_photos.HIT_TTL),
        (httpx.Response(404), False, employee_photos.MISS_TTL),        # no photo / no Microsoft 365-style account
        (httpx.Response(503, headers={"Retry-After": "40"}), False, 40),  # throttled source
        (httpx.Response(401), False, 300),                              # auth failure: initials, retry later
        (httpx.ConnectError("down"), False, 120),
    ]
    for resp, has, ttl in cases:
        monkeypatch.setattr(workforce_directory, "_client", lambda r=resp: Client(r))
        photo, got_ttl = employee_photos._fetch_upstream("b1")
        assert (photo is not None, got_ttl) == (has, ttl)


# --- photo route ---------------------------------------------------------------

def test_photo_route_serves_only_verified_single_matches(api_client, db, audit_calls, photo_directory, monkeypatch):
    employee_photos.cache.clear()
    seen = []
    monkeypatch.setattr(employee_photos.cache, "_fetch", lambda bid: (seen.append(bid), (Photo(PNG, "image/png"), 60))[1])
    ok = _get(api_client, "/api/onsite/employees/101/photo")
    assert ok.status_code == 200 and ok.content == PNG
    assert ok.headers["cache-control"] == "private, max-age=86400"
    assert _get(api_client, "/api/onsite/employees/105/photo").status_code == 404   # ambiguous number: never guessed
    assert _get(api_client, "/api/onsite/employees/999/photo").status_code == 404   # unmatched code
    assert _get(api_client, "/api/onsite/employees/102/photo").status_code == 404   # matched, no photo
    for _ in range(3):
        _get(api_client, "/api/onsite/employees/101/photo")
    assert len(seen) == 1  # cached: refreshes never re-download
    employee_photos.cache.clear()


def test_photo_route_requires_attendance_permission(api_client, db, audit_calls, photo_directory):
    assert api_client.get("/api/onsite/employees/101/photo").status_code == 401
    resp = api_client.get("/api/onsite/employees/101/photo", headers=headers_for(None))
    assert resp.status_code == 403


def test_photo_unavailable_when_directory_down(api_client, db, audit_calls, monkeypatch):
    monkeypatch.setattr(workforce_directory, "load", lambda force=False: workforce_directory.DirectorySnapshot(available=False))
    assert _get(api_client, "/api/onsite/employees/101/photo").status_code == 404


def test_has_photo_flag_in_dtos(api_client, db, audit_calls, photo_directory):
    _ready(api_client)
    url = f"/api/onsite/employees?site_id=dev-site&date_from={DAY1}&date_to={DAY2}&page_size=50"
    rows = _get(api_client, url).json()["items"]
    flags = {r["emp_code"]: r["has_photo"] for r in rows}
    assert flags["101"] is True and flags["102"] is False and flags.get("105") is False
    act = _get(api_client, f"/api/onsite/activity?site_id=dev-site&date_from={DAY1}&date_to={DAY1}&emp_code=101").json()
    assert all(e["has_photo"] for e in act["items"])


# --- hour drill-down -------------------------------------------------------------

def test_hour_windows_use_site_time_zone():
    w = svc.hour_windows(date(2026, 11, 3), date(2026, 11, 4), 11, "Asia/Colombo")
    assert w == [(datetime(2026, 11, 3, 5, 30), datetime(2026, 11, 3, 6, 30)),
                 (datetime(2026, 11, 4, 5, 30), datetime(2026, 11, 4, 6, 30))]


def test_hour_drilldown_matches_hourly_chart(api_client, db, audit_calls, directory):
    _ready(api_client)
    for rng in (f"date_from={DAY1}&date_to={DAY1}", f"date_from={DAY1}&date_to={DAY2}"):
        hours = _get(api_client, f"/api/onsite/dashboard/hourly-activity?site_id=dev-site&{rng}").json()["hours"]
        for h in hours:
            got = _get(api_client, f"/api/onsite/activity?site_id=dev-site&{rng}&hour={h['hour']}").json()
            assert got["total"] == h["events"], (rng, h)
            assert len({e["emp_code"] for e in got["items"]}) <= h["employees"]


def _add(db, event_id, utc):
    db.add(AttendanceEvent(
        event_id=event_id, site_id="dev-site", source_epoch=1, source_transaction_id=hash(event_id) % 10**9, emp_code="101",
        emp_id=None, punch_time_local="x", punch_time_utc=utc, time_zone="Asia/Colombo", punch_state="255", verify_type=1,
        work_code=None, terminal_sn="T", terminal_alias="Main Door", area_alias=None, source=1, is_attendance=True,
        upload_time_utc=utc, captured_at_utc=utc, received_utc=utc, batch_id="b", record_hash="h",
        site_local_date=date(2026, 10, 20), tz_consistent=True, sync_run_id="t", mirrored_at=utc))
    db.commit()


def test_hour_boundaries_inclusive_start_exclusive_end(api_client, db, audit_calls, directory):
    _ready(api_client)
    _add(db, "edge-start", datetime(2026, 10, 20, 5, 30, 0))      # 11:00:00 Colombo -> hour 11
    _add(db, "edge-last", datetime(2026, 10, 20, 6, 29, 59))      # 11:59:59 -> hour 11
    _add(db, "edge-next", datetime(2026, 10, 20, 6, 30, 0))       # 12:00:00 -> hour 12 only
    base = "/api/onsite/activity?site_id=dev-site&date_from=2026-10-20&date_to=2026-10-20"
    assert _get(api_client, base + "&hour=11", "ONSITE_ADMIN").json()["total"] == 2
    h12 = _get(api_client, base + "&hour=12", "ONSITE_ADMIN").json()
    assert [e["event_id"] for e in h12["items"]] == ["edge-next"]
    assert _get(api_client, base + "&hour=24").status_code == 422


def test_activity_sort_paging_and_review_flags(api_client, db, audit_calls, directory):
    _ready(api_client)
    base = f"/api/onsite/activity?site_id=dev-site&date_from={DAY1}&date_to={DAY2}"
    default = _get(api_client, base).json()
    assert default["page_size"] == 10
    newest = [e["local_time"] for e in _get(api_client, base + "&page_size=50").json()["items"]]
    oldest = [e["local_time"] for e in _get(api_client, base + "&page_size=50&sort=time").json()["items"]]
    assert oldest == list(reversed(newest))
    p1 = _get(api_client, base + "&page_size=3&page=1").json()["items"]
    p2 = _get(api_client, base + "&page_size=3&page=2").json()["items"]
    assert not {(e["local_time"], e["emp_code"]) for e in p1} & {(e["local_time"], e["emp_code"]) for e in p2}
    dup = [e for e in _get(api_client, base + "&page_size=50&emp_code=0107").json()["items"]]
    assert dup and all("POSSIBLE_DUPLICATE_TAP" in e["review_flags"] for e in dup)


def test_employee_detail_can_skip_events(api_client, db, audit_calls, directory):
    _ready(api_client)
    url = f"/api/onsite/employees/101?site_id=dev-site&date_from={DAY1}&date_to={DAY2}"
    full, lazy = _get(api_client, url).json(), _get(api_client, url + "&include_events=false").json()
    assert full["events"] and lazy["events"] == []
    assert lazy["days"] == full["days"] and lazy["summary"] == full["summary"]


def test_identity_match_pages_server_side(api_client, db, audit_calls, directory):
    _ready(api_client)
    whole = _get(api_client, "/api/onsite/admin/identity-match", "ONSITE_ADMIN").json()
    page = _get(api_client, "/api/onsite/admin/identity-match?page=1&page_size=2", "ONSITE_ADMIN").json()
    assert page["total"] == len(whole["rows"]) and len(page["rows"]) == 2 and page["summary"] == whole["summary"]
    un = _get(api_client, "/api/onsite/admin/identity-match?page=1&identity_class=UNMATCHED", "ONSITE_ADMIN").json()
    assert un["total"] >= 1 and all(r["identity_class"] == "UNMATCHED" for r in un["rows"])


def test_default_page_size_is_10(api_client, db, audit_calls, directory):
    _ready(api_client)
    for path in (f"/api/onsite/today?site_id=dev-site&date={DAY1}",
                 f"/api/onsite/employees?site_id=dev-site&date_from={DAY1}&date_to={DAY2}",
                 f"/api/onsite/exceptions?site_id=dev-site&date_from={DAY1}&date_to={DAY2}"):
        assert _get(api_client, path).json()["page_size"] == 10


def test_activity_export_applies_the_hour_filter(api_client, db, audit_calls, directory):
    import io

    from openpyxl import load_workbook

    _ready(api_client)
    base = f"/api/onsite/activity/export?site_id=dev-site&date_from={DAY1}&date_to={DAY1}"
    total = _get(api_client, f"/api/onsite/activity?site_id=dev-site&date_from={DAY1}&date_to={DAY1}&hour=8").json()["total"]
    def rows(url):
        wb = load_workbook(io.BytesIO(_get(api_client, url).content))
        return sum(ws.max_row for ws in wb.worksheets)

    everything = _get(api_client, f"/api/onsite/activity?site_id=dev-site&date_from={DAY1}&date_to={DAY1}").json()["total"]
    assert 0 < total < everything
    assert rows(base + "&hour=8") < rows(base)  # the hour filter reaches the export
