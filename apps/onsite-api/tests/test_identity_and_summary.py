"""Legacy Identity Match report (shape kept, verified-mapping semantics) and
neutral daily facts/flags. Employee Number equality NEVER attributes."""

from datetime import date

from app.services import workforce_directory
from app.services.attendance_summary import daily_activity
from tests.conftest import DIRECTORY, enable_site, headers_for, make_mapping, map_directory, run_sync


def _report(api_client, fmt="json"):
    return api_client.get(f"/api/onsite/admin/identity-match?format={fmt}", headers=headers_for())


def test_identity_report_without_mappings_matches_nobody(api_client, db, audit_calls, directory):
    """Before any verification every code is UNMATCHED — even codes equal to an Employee Number."""
    run_sync(api_client)
    enable_site(api_client, "dev-site")
    enable_site(api_client, "syd-site")
    report = _report(api_client).json()
    assert {r["identity_class"] for r in report["rows"]} == {"UNMATCHED"}
    assert all(r["matches"] == [] for r in report["rows"])


def test_identity_classes_from_verified_mappings(api_client, db, audit_calls, directory):
    map_directory(DIRECTORY)
    run_sync(api_client)
    enable_site(api_client, "dev-site")
    enable_site(api_client, "syd-site")
    report = _report(api_client).json()
    classes = {r["emp_code"]: r["identity_class"] for r in report["rows"]}
    assert classes == {
        "101": "MATCHED_ACTIVE", "102": "MATCHED_ACTIVE", "0107": "MATCHED_ACTIVE",
        "103": "MATCHED_INACTIVE", "105": "UNMATCHED", "108": "MATCHED_BEFORE_HIRE",
        "110": "MATCHED_ACTIVE", "999": "UNMATCHED", "TEST-AZURE-001": "UNMATCHED",
    }
    assert "AMBIGUOUS" not in classes.values()  # never produced any more
    s = report["summary"]
    assert [s[k] for k in ("MATCHED_ACTIVE", "MATCHED_INACTIVE", "MATCHED_BEFORE_HIRE", "AMBIGUOUS", "UNMATCHED")] == [
        4, 1, 1, 0, 3]
    assert s["directory_total"] == 9 and s["directory_blank_employee_numbers"] == 1


def test_shared_employee_number_mapped_to_one_person(api_client, db, audit_calls, directory):
    make_mapping(db, code="105", bamboohr_id="6", valid_from="2020-01-01")  # E, not D (both have number 105)
    run_sync(api_client)
    enable_site(api_client, "dev-site")
    row = next(r for r in _report(api_client).json()["rows"] if r["emp_code"] == "105")
    assert row["identity_class"] == "MATCHED_ACTIVE" and [m["bamboohr_id"] for m in row["matches"]] == ["6"]


def test_report_only_covers_enabled_sites(api_client, db, audit_calls, directory):
    run_sync(api_client)
    assert _report(api_client).json()["rows"] == []
    enable_site(api_client, "syd-site")
    assert {r["emp_code"] for r in _report(api_client).json()["rows"]} == {"110", "108"}


def test_identity_csv(api_client, db, audit_calls, directory):
    map_directory(DIRECTORY)
    run_sync(api_client)
    enable_site(api_client, "dev-site")
    resp = _report(api_client, "csv")
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0] == "emp_code,identity_class,event_count,first_seen,last_seen,match_count,bamboohr_ids,employment_status"
    assert any(line.startswith("101,MATCHED_ACTIVE,") and ",1,1," in line for line in lines)
    assert any(line.startswith("105,UNMATCHED,") for line in lines)
    assert "display_name" not in resp.text


def test_people_unavailable_codes_only(api_client, db, audit_calls, monkeypatch):
    run_sync(api_client)
    enable_site(api_client, "dev-site")
    workforce_directory.clear_cache()  # PEOPLE_API_URL points at an unreachable port
    report = _report(api_client).json()
    assert report["directory_available"] is False
    assert {r["emp_code"] for r in report["rows"]} >= {"101", "999"}
    assert all(r["identity_class"] is None for r in report["rows"])
    monkeypatch.setattr(workforce_directory, "_client", lambda: None)  # PEOPLE_API_URL unset
    assert workforce_directory.load(force=True).available is False


def test_daily_activity_neutral_facts_and_flags(api_client, db, audit_calls, directory):
    map_directory(DIRECTORY)
    run_sync(api_client)
    enable_site(api_client, "dev-site")
    rows = daily_activity(
        db, allowed_site_ids=("dev-site",), site_id="dev-site", site_time_zone="Asia/Colombo",
        date_from=date(2026, 10, 13), date_to=date(2026, 10, 14), directory=directory, today=date(2026, 10, 22),
    )
    by = {(r["local_date"], r["emp_code"]): r for r in rows}
    a = by[("2026-10-13", "101")]
    assert a["punch_count"] == 2 and a["span_minutes"] == 540 and a["flags"] == [] and a["bamboohr_id"] == "1"
    assert by[("2026-10-13", "102")]["flags"] == ["SINGLE_PUNCH"]
    assert "POSSIBLE_DUPLICATE_TAP" in by[("2026-10-13", "0107")]["flags"]
    assert "INACTIVE_EMPLOYEE_ACTIVITY" in by[("2026-10-14", "103")]["flags"]
    # Unverified codes are not rows at all (no UNMATCHED/AMBIGUOUS flags any more).
    assert not {k for k in by if k[1] in ("999", "105", "TEST-AZURE-001")}
    for r in rows:  # no policy judgements in V1
        assert not set(r) & {"present", "absent", "late", "early", "worked_hours", "status"}

    syd = daily_activity(
        db, allowed_site_ids=("dev-site", "syd-site"), site_id="syd-site", site_time_zone="Australia/Sydney",
        date_from=date(2026, 10, 14), date_to=date(2026, 10, 15), directory=directory, today=date(2026, 10, 22),
    )
    flags = {(r["local_date"], r["emp_code"]): r["flags"] for r in syd}
    assert "BEFORE_HIRE_ACTIVITY" in flags[("2026-10-15", "108")]
    assert "TZ_INCONSISTENT" in flags[("2026-10-15", "108")]


def test_daily_activity_respects_site_allow_list(db, directory):
    map_directory(DIRECTORY)
    assert daily_activity(
        db, allowed_site_ids=(), site_id="dev-site", site_time_zone="Asia/Colombo",
        date_from=date(2026, 10, 13), date_to=date(2026, 10, 14), directory=directory,
    ) == []
