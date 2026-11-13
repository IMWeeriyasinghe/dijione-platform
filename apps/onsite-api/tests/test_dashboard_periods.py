"""Period Overview/hourly (date ranges) and server-side sorting for the
redesigned dashboard. Ranges stay bounded and site-scoped."""

from tests.conftest import DIRECTORY, enable_site, headers_for, map_directory, run_sync

DAY1, DAY2 = "2026-10-13", "2026-10-14"


def _ready(api_client):
    map_directory(DIRECTORY)
    run_sync(api_client)
    enable_site(api_client, "dev-site")


def _get(api_client, path, role="ONSITE_VIEWER"):
    return api_client.get(path, headers=headers_for(role))


def test_single_day_overview_is_unchanged_by_range_support(api_client, db, audit_calls, directory):
    _ready(api_client)
    one = _get(api_client, f"/api/onsite/dashboard/overview?site_id=dev-site&date={DAY1}").json()
    same = _get(api_client, f"/api/onsite/dashboard/overview?site_id=dev-site&date_from={DAY1}&date_to={DAY1}").json()
    assert one["kpis"] == same["kpis"]
    assert (one["date_from"], one["date_to"]) == (DAY1, DAY1)
    assert one["kpis"]["activity_days"] == 1


def test_range_overview_counts_distinct_employees(api_client, db, audit_calls, directory):
    _ready(api_client)
    d1 = _get(api_client, f"/api/onsite/dashboard/overview?site_id=dev-site&date={DAY1}").json()["kpis"]
    d2 = _get(api_client, f"/api/onsite/dashboard/overview?site_id=dev-site&date={DAY2}").json()["kpis"]
    both = _get(api_client, f"/api/onsite/dashboard/overview?site_id=dev-site&date_from={DAY1}&date_to={DAY2}").json()
    k = both["kpis"]
    assert (both["date_from"], both["date_to"]) == (DAY1, DAY2)
    assert k["total_events"] == d1["total_events"] + d2["total_events"]
    # Distinct employees across the period, never a sum of per-day counts.
    assert max(d1["employees_with_activity"], d2["employees_with_activity"]) <= k["employees_with_activity"]
    assert k["employees_with_activity"] <= d1["employees_with_activity"] + d2["employees_with_activity"]
    assert k["activity_days"] == sum(1 for d in (d1, d2) if d["total_events"])


def test_range_hourly_sums_events(api_client, db, audit_calls, directory):
    _ready(api_client)
    h1 = _get(api_client, f"/api/onsite/dashboard/hourly-activity?site_id=dev-site&date={DAY1}").json()["hours"]
    h2 = _get(api_client, f"/api/onsite/dashboard/hourly-activity?site_id=dev-site&date={DAY2}").json()["hours"]
    hr = _get(api_client, f"/api/onsite/dashboard/hourly-activity?site_id=dev-site&date_from={DAY1}&date_to={DAY2}").json()
    assert len(hr["hours"]) == 24
    assert [h["events"] for h in hr["hours"]] == [a["events"] + b["events"] for a, b in zip(h1, h2, strict=True)]


def test_range_is_capped_and_scoped(api_client, db, audit_calls, directory):
    _ready(api_client)
    resp = _get(api_client, "/api/onsite/dashboard/overview?site_id=dev-site&date_from=2026-01-01&date_to=2026-10-14")
    assert resp.status_code == 422  # beyond the 92-day cap
    assert _get(api_client, f"/api/onsite/dashboard/overview?site_id=syd-site&date_from={DAY1}&date_to={DAY2}").status_code == 404


def test_employee_sorting(api_client, db, audit_calls, directory):
    _ready(api_client)
    base = f"/api/onsite/employees?site_id=dev-site&date_from={DAY1}&date_to={DAY2}&activity=with_activity"
    by_events = _get(api_client, base).json()["items"]
    assert [r["events"] for r in by_events] == sorted((r["events"] for r in by_events), reverse=True)
    asc = _get(api_client, base + "&sort=events").json()["items"]
    assert [r["events"] for r in asc] == sorted(r["events"] for r in asc)
    names = [((r["employee_name"] or "~").lower()) for r in _get(api_client, base + "&sort=employee").json()["items"]]
    assert names == sorted(names)
    assert _get(api_client, base + "&sort=salary").status_code == 422


def test_exception_sorting(api_client, db, audit_calls, directory):
    _ready(api_client)
    base = f"/api/onsite/exceptions?site_id=dev-site&date_from={DAY1}&date_to={DAY2}"
    items = _get(api_client, base + "&sort=-flags").json()["items"]
    assert [len(i["flags"]) for i in items] == sorted((len(i["flags"]) for i in items), reverse=True)
    dates = [i["local_date"] for i in _get(api_client, base + "&sort=date").json()["items"]]
    assert dates == sorted(dates)


def test_employee_summary_describes_population_before_activity_filter(api_client, db, audit_calls, directory):
    _ready(api_client)
    base = f"/api/onsite/employees?site_id=dev-site&date_from={DAY1}&date_to={DAY2}"
    everyone = _get(api_client, base).json()
    with_act = _get(api_client, base + "&activity=with_activity").json()
    s = with_act["summary"]
    assert s == everyone["summary"]  # the activity filter never changes the population summary
    assert s["with_activity"] == with_act["total"]
    assert s["employees"] >= s["with_activity"] and s["employees"] >= s["active"] + s["inactive"]
