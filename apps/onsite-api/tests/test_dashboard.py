"""Dashboard V1 API: server-side aggregates, site scoping, permissions,
people-api fallback, raw PunchState preservation, neutral wording."""

import json

from app.services import workforce_directory
from tests.conftest import enable_site, headers_for, run_sync

DAY1, DAY2 = "2026-10-13", "2026-10-14"
VIEWER_PATHS = [
    "/api/onsite/sites", f"/api/onsite/dashboard/overview?date={DAY1}", f"/api/onsite/dashboard/hourly-activity?date={DAY1}",
    "/api/onsite/dashboard/activity-trend?days=7", "/api/onsite/dashboard/recent-activity",
    f"/api/onsite/today?date={DAY1}", f"/api/onsite/activity?date_from={DAY1}&date_to={DAY2}",
    f"/api/onsite/employees?date_from={DAY1}&date_to={DAY2}", f"/api/onsite/exceptions?date_from={DAY1}&date_to={DAY2}",
]


def _ready(api_client, *sites):
    run_sync(api_client)
    for s in sites or ("dev-site",):
        enable_site(api_client, s)


def _get(api_client, path, role="ONSITE_VIEWER"):
    return api_client.get(path, headers=headers_for(role))


def test_overview_aggregates(api_client, db, audit_calls, directory):
    _ready(api_client)
    body = _get(api_client, f"/api/onsite/dashboard/overview?site_id=dev-site&date={DAY1}").json()
    k = body["kpis"]
    # 2026-10-13 at dev-site: 101 x2, 102 x1, 0107 x2 (dup tap), 999 x1 (unmatched)
    assert (k["employees_with_activity"], k["total_events"]) == (4, 6)
    assert k["single_punch_employees"] == 2 and k["unmatched_codes"] == 1
    assert k["employees_needing_review"] == 3
    assert body["review_breakdown"]["POSSIBLE_DUPLICATE_TAP"] == 1
    assert set(body["review_breakdown"]) == {
        "SINGLE_PUNCH", "HIGH_PUNCH_COUNT", "POSSIBLE_DUPLICATE_TAP", "UNMATCHED_CODE", "AMBIGUOUS_CODE",
        "INACTIVE_EMPLOYEE_ACTIVITY", "BEFORE_HIRE_ACTIVITY", "TZ_INCONSISTENT",
    }
    assert body["time_zone"] == "Asia/Colombo" and k["feed_state"]


def test_default_site_and_date(api_client, db, audit_calls, directory):
    _ready(api_client)
    body = _get(api_client, "/api/onsite/dashboard/overview").json()
    assert body["site_id"] == "dev-site" and body["date"]  # first enabled site, site-local today


def test_hourly_grouping_uses_site_local_hour(api_client, db, audit_calls, directory):
    _ready(api_client)
    hours = _get(api_client, f"/api/onsite/dashboard/hourly-activity?date={DAY1}").json()["hours"]
    assert len(hours) == 24
    by = {h["hour"]: h["events"] for h in hours}
    assert by[8] == 5  # 03:00-03:09 UTC = 08:30-08:39 Colombo
    assert by[17] == 1  # +9h
    assert sum(by.values()) == 6


def test_activity_trend_range(api_client, db, audit_calls, directory):
    _ready(api_client)
    body = _get(api_client, f"/api/onsite/dashboard/activity-trend?days=2&date_to={DAY2}").json()
    assert [(d["date"], d["events"]) for d in body["days"]] == [(DAY1, 6), (DAY2, 4)]
    assert _get(api_client, "/api/onsite/dashboard/activity-trend?days=200").status_code == 422


def test_today_grouping_filters_and_sort(api_client, db, audit_calls, directory):
    _ready(api_client)
    body = _get(api_client, f"/api/onsite/today?date={DAY1}&sort=-punch_count").json()
    assert body["total"] == 4
    first = body["items"][0]
    assert first["punch_count"] == 2 and first["terminal_names"] == ["Main Door"]
    assert set(first) >= {"employee_name", "department", "first_activity_local", "latest_activity_local", "span_minutes"}
    review = _get(api_client, f"/api/onsite/today?date={DAY1}&review=needs_review").json()
    assert review["total"] == 3
    search = _get(api_client, f"/api/onsite/today?date={DAY1}&q=0107").json()
    assert [r["emp_code"] for r in search["items"]] == ["0107"]
    assert _get(api_client, f"/api/onsite/today?date={DAY1}&review=LATE").status_code == 422


def test_activity_explorer_filters_and_raw_punch_state(api_client, db, audit_calls, directory):
    _ready(api_client)
    body = _get(api_client, f"/api/onsite/activity?date_from={DAY1}&date_to={DAY2}&page_size=5").json()
    assert body["total"] == 10 and len(body["items"]) == 5
    assert {i["punch_state_raw"] for i in body["items"]} == {"255"}  # raw, never IN/OUT
    assert "event_id" not in body["items"][0]  # technical fields are admin-only
    admin = _get(api_client, f"/api/onsite/activity?date_from={DAY1}&date_to={DAY2}", "ONSITE_ADMIN").json()
    assert {"event_id", "source_epoch", "record_hash"} <= set(admin["items"][0])
    unmatched = _get(api_client, f"/api/onsite/activity?date_from={DAY1}&date_to={DAY2}&identity_class=UNMATCHED").json()
    assert {i["emp_code"] for i in unmatched["items"]} == {"999", "TEST-AZURE-001"}
    dup = _get(api_client, f"/api/onsite/activity?date_from={DAY1}&date_to={DAY2}&flag=POSSIBLE_DUPLICATE_TAP").json()
    assert {i["emp_code"] for i in dup["items"]} == {"0107"}
    csv = _get(api_client, f"/api/onsite/activity?date_from={DAY1}&date_to={DAY2}&format=csv")
    assert csv.headers["content-type"].startswith("text/csv") and len(csv.text.strip().splitlines()) == 11
    assert _get(api_client, "/api/onsite/activity?date_from=2026-01-01&date_to=2026-10-14").status_code == 422


def test_employees_and_detail(api_client, db, audit_calls, directory):
    _ready(api_client)
    body = _get(api_client, f"/api/onsite/employees?date_from={DAY1}&date_to={DAY2}&page_size=200").json()
    rows = {r["emp_code"]: r for r in body["items"]}
    assert rows["101"]["events"] == 3 and rows["101"]["activity_days"] == 2
    assert rows["999"]["in_directory"] is False  # unmatched attendance codes stay visible
    assert rows["110"]["events"] == 0  # syd-site not enabled -> no activity counted here
    detail = _get(api_client, f"/api/onsite/employees/0107?date_from={DAY1}&date_to={DAY2}").json()
    assert detail["summary"] == {"activity_days": 1, "events": 2, "review_flags": 1}
    assert detail["days"][0]["flags"] == ["POSSIBLE_DUPLICATE_TAP"] and len(detail["events"]) == 2
    assert _get(api_client, f"/api/onsite/employees/nobody?date_from={DAY1}&date_to={DAY2}").status_code == 404


def test_exceptions_queue(api_client, db, audit_calls, directory):
    _ready(api_client)
    body = _get(api_client, f"/api/onsite/exceptions?date_from={DAY1}&date_to={DAY2}").json()
    assert body["counts"]["UNMATCHED_CODE"] == 2 and body["counts"]["INACTIVE_EMPLOYEE_ACTIVITY"] == 1
    assert all(i["reasons"] and i["flags"] for i in body["items"])
    only = _get(api_client, f"/api/onsite/exceptions?date_from={DAY1}&date_to={DAY2}&flag=AMBIGUOUS_CODE").json()
    assert [i["emp_code"] for i in only["items"]] == ["105"]
    text = json.dumps(body).lower()
    for word in ("absent", "\"late\"", "present", "worked_hours"):
        assert word not in text


def test_site_scoping_404_and_isolation(api_client, db, audit_calls, directory):
    run_sync(api_client)
    for path in VIEWER_PATHS[1:]:  # no enabled site at all
        assert _get(api_client, path).status_code == 404, path
    assert _get(api_client, "/api/onsite/sites").json() == []
    enable_site(api_client, "dev-site")
    assert _get(api_client, f"/api/onsite/today?site_id=syd-site&date={DAY2}").status_code == 404  # disabled
    assert _get(api_client, f"/api/onsite/today?site_id=nowhere&date={DAY2}").status_code == 404  # unknown
    sites = _get(api_client, "/api/onsite/sites").json()
    assert [s["site_id"] for s in sites] == ["dev-site"] and sites[0]["last_activity_date"] == "2026-10-14"


def test_permissions(api_client, db, audit_calls, directory):
    _ready(api_client)
    for path in VIEWER_PATHS:
        assert _get(api_client, path, "ONSITE_VIEWER").status_code == 200, path
        assert api_client.get(path, headers=headers_for(None)).status_code == 403, path
        assert api_client.get(path).status_code == 401, path


def test_people_unavailable_codes_only(api_client, db, audit_calls):
    _ready(api_client)
    workforce_directory.clear_cache()  # PEOPLE_API_URL points at an unreachable port
    today = _get(api_client, f"/api/onsite/today?date={DAY1}").json()
    assert today["directory_available"] is False and today["total"] == 4
    assert all(r["employee_name"] is None for r in today["items"])
    overview = _get(api_client, f"/api/onsite/dashboard/overview?date={DAY1}").json()
    assert overview["kpis"]["total_events"] == 6 and overview["kpis"]["unmatched_codes"] == 0
