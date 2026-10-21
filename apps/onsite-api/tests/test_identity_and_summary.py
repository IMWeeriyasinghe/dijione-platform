"""Identity match (exact string equality, all classes, CSV, codes-only when
people-api is unavailable) and neutral daily facts/flags."""

from datetime import date

from app.services import workforce_directory
from app.services.attendance_summary import daily_activity
from app.services.identity_match_service import classify
from tests.conftest import enable_site, headers_for, run_sync


def _report(api_client, fmt="json"):
    return api_client.get(f"/api/onsite/admin/identity-match?format={fmt}", headers=headers_for())


def test_identity_classes(api_client, db, audit_calls, directory):
    run_sync(api_client)
    enable_site(api_client, "dev-site")
    enable_site(api_client, "syd-site")
    report = _report(api_client).json()
    assert report["directory_available"] is True
    classes = {r["emp_code"]: r["identity_class"] for r in report["rows"]}
    assert classes == {
        "101": "MATCHED_ACTIVE", "102": "MATCHED_ACTIVE", "0107": "MATCHED_ACTIVE",
        "103": "MATCHED_INACTIVE", "105": "AMBIGUOUS", "108": "MATCHED_BEFORE_HIRE",
        "110": "MATCHED_ACTIVE", "999": "UNMATCHED", "TEST-AZURE-001": "UNMATCHED",
    }
    s = report["summary"]
    counts = [s[k] for k in ("MATCHED_ACTIVE", "MATCHED_INACTIVE", "MATCHED_BEFORE_HIRE", "AMBIGUOUS", "UNMATCHED")]
    assert counts == [4, 1, 1, 1, 2]
    assert s["directory_total"] == 9 and s["directory_blank_employee_numbers"] == 1
    assert s["directory_duplicate_employee_numbers"] == 1
    assert s["directory_entries_without_attendance"] == 1  # the blank-number entry


def test_matching_is_exact_string_equality():
    entries = [{"bamboohr_id": "7", "employee_number": "0107", "employment_status": "Active", "hire_date": None}]
    snap = workforce_directory.DirectorySnapshot(True, entries)
    index = snap.by_employee_number()
    assert "0107" in index
    for variant in ("107", " 0107", "0107 ", "00107"):
        assert variant not in index
    assert classify(index.get("107", []), date(2026, 1, 1), date(2026, 1, 1)).value == "UNMATCHED"


def test_report_only_covers_enabled_sites(api_client, db, audit_calls, directory):
    run_sync(api_client)
    assert _report(api_client).json()["rows"] == []
    enable_site(api_client, "syd-site")
    assert {r["emp_code"] for r in _report(api_client).json()["rows"]} == {"110", "108"}


def test_identity_csv(api_client, db, audit_calls, directory):
    run_sync(api_client)
    enable_site(api_client, "dev-site")
    resp = _report(api_client, "csv")
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0] == "emp_code,identity_class,event_count,first_seen,last_seen,match_count,bamboohr_ids,employment_status"
    assert any(line.startswith("105,AMBIGUOUS,") and "5;6" in line for line in lines)
    assert "display_name" not in resp.text  # no names in the export


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
    run_sync(api_client)
    enable_site(api_client, "dev-site")
    rows = daily_activity(
        db, allowed_site_ids=("dev-site",), site_id="dev-site", site_time_zone="Asia/Colombo",
        date_from=date(2026, 10, 13), date_to=date(2026, 10, 14), directory=directory, today=date(2026, 10, 22),
    )
    by = {(r["local_date"], r["emp_code"]): r for r in rows}
    a = by[("2026-10-13", "101")]
    assert a["punch_count"] == 2 and a["span_minutes"] == 540 and a["flags"] == []
    assert by[("2026-10-13", "102")]["flags"] == ["SINGLE_PUNCH"]
    assert "POSSIBLE_DUPLICATE_TAP" in by[("2026-10-13", "0107")]["flags"]
    assert "UNMATCHED_CODE" in by[("2026-10-13", "999")]["flags"]
    assert "INACTIVE_EMPLOYEE_ACTIVITY" in by[("2026-10-14", "103")]["flags"]
    assert "AMBIGUOUS_CODE" in by[("2026-10-14", "105")]["flags"]
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
    assert daily_activity(
        db, allowed_site_ids=(), site_id="dev-site", site_time_zone="Asia/Colombo",
        date_from=date(2026, 10, 13), date_to=date(2026, 10, 14), directory=directory,
    ) == []
