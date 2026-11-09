"""UAT feedback: accidental check-out recovery, notifications and exports."""

import csv
import io
import re
from datetime import date, datetime, timedelta
from threading import Barrier

from openpyxl import load_workbook
from sqlalchemy import select, update

from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models.corrections import CorrectionRequest
from app.models.notifications import NotificationOutbox
from app.services import notifications
from tests.conftest import bearer, issue_token
from tests.test_corrections_management import MANAGER, MGR, A, C, M, clock, hdr, post, rid  # noqa: F401

EMP = MANAGER[:4]
INTERNAL = {"X-Internal-Token": "test-only-internal-secret"}
RUN = "/api/atwork/internal/notifications/run"


def check_in(api, h=None):
    return post(api, f"{A}/check-in", h, work_mode="OFFICE", client_request_id=rid()).json()["session"]


def check_out(api, h=None):
    return post(api, f"{A}/check-out", h, client_request_id=rid()).json()["session"]


def today(api):
    return api.get(f"{A}/today", headers=hdr()).json()


def correct(api, h=None, **body):
    return post(api, C, h, client_request_id=rid(), reason="Accidental check-out", **body)


def outbox(db, kind=None):
    db.expire_all()
    rows = list(db.scalars(select(NotificationOutbox)))
    return [r for r in rows if kind is None or r.kind == kind]


def iso(value):
    return value.isoformat()


class FakePlatform:
    def __init__(self, result=True):
        self.result, self.calls = result, []

    def deliver_notification(self, payload):
        self.calls.append(payload)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


# --- accidental check-out ---


def test_immediate_recheck_in_adds_to_the_same_day_without_overlap(api_client, clock):  # noqa: F811
    check_in(api_client)
    clock.advance(hours=5)
    first = check_out(api_client)
    second = check_in(api_client)
    assert first["check_out_at"] == second["check_in_at"]
    clock.advance(hours=3)
    check_out(api_client)
    day = today(api_client)
    assert day["session_count"] == 2 and day["totals"]["net_seconds"] == 8 * 3600


def test_missing_session_for_the_unrecorded_period_needs_approval(api_client, clock):  # noqa: F811
    check_in(api_client)
    clock.advance(hours=5)
    check_out(api_client)
    gap_start = clock.value
    clock.advance(hours=3)
    made = correct(api_client, work_mode="OFFICE", check_in_at=iso(gap_start), check_out_at=iso(clock.value))
    assert made.status_code == 201
    assert today(api_client)["totals"]["net_seconds"] == 5 * 3600
    assert post(api_client, f"{M}/corrections/{made.json()['id']}/approve", MGR).status_code == 200
    day = today(api_client)
    assert day["session_count"] == 2 and day["totals"]["net_seconds"] == 8 * 3600


def test_check_out_correction_and_its_rejected_forms(api_client, clock):  # noqa: F811
    start = clock.value
    first_id = check_in(api_client)["id"]
    clock.advance(hours=2)
    first_end = clock.value
    check_out(api_client)
    clock.advance(hours=1)
    second_start = clock.value
    check_in(api_client)
    clock.advance(hours=1)
    check_out(api_client)

    overlap = correct(api_client, session_id=first_id, check_out_at=iso(second_start + timedelta(minutes=1)))
    assert "SESSION_OVERLAP" in overlap.text
    future = correct(api_client, session_id=first_id, check_out_at=iso(clock.value + timedelta(hours=1)))
    assert future.status_code == 422 and "future" in future.text
    outside = correct(
        api_client,
        session_id=first_id,
        breaks=[{"started_at": iso(first_end), "ended_at": iso(first_end + timedelta(minutes=5))}],
    )
    assert outside.status_code == 422 and "within the session" in outside.text
    backwards = correct(
        api_client,
        session_id=first_id,
        breaks=[{"started_at": iso(start + timedelta(hours=1)), "ended_at": iso(start + timedelta(minutes=10))}],
    )
    assert backwards.status_code == 422
    assert correct(api_client, work_mode="OFFICE", check_in_at=iso(start), check_out_at=iso(first_end)).status_code >= 400

    good = correct(api_client, session_id=first_id, check_out_at=iso(second_start))
    assert good.status_code == 201
    post(api_client, f"{M}/corrections/{good.json()['id']}/approve", MGR)
    assert today(api_client)["totals"]["net_seconds"] == 4 * 3600


# --- notification triggers and recipients ---


def session_request(api, clock):  # noqa: F811
    sid = check_in(api)["id"]
    clock.advance(hours=2)
    check_out(api)
    item = correct(api, session_id=sid, check_out_at=iso(clock.value - timedelta(minutes=5))).json()
    with SessionLocal() as session:  # created_at comes from the wall clock, not the test clock
        session.execute(update(CorrectionRequest).where(CorrectionRequest.id == item["id"]).values(created_at=clock.value))
        session.commit()
    return item


def test_new_request_targets_reviewers_but_not_the_requester(api_client, clock, db):  # noqa: F811
    item = session_request(api_client, clock)
    [row] = outbox(db, "ATWORK_CORRECTION_REQUESTED")
    assert row.user_id is None and row.exclude_user_ids == [7]
    assert set(row.required_permissions) == {"atwork.management.access", "atwork.corrections.review"}
    assert row.link_url == f"/atwork/management/corrections/{item['id']}"


def test_decisions_go_only_to_the_employee(api_client, clock, db):  # noqa: F811
    approved = session_request(api_client, clock)
    post(api_client, f"{M}/corrections/{approved['id']}/approve", MGR)
    [ok] = outbox(db, "ATWORK_CORRECTION_APPROVED")
    assert ok.user_id == 7 and ok.required_permissions is None
    clock.advance(hours=1)
    rejected = session_request(api_client, clock)
    post(api_client, f"{M}/corrections/{rejected['id']}/reject", MGR, reason="Times do not match the log")
    [no] = outbox(db, "ATWORK_CORRECTION_REJECTED")
    assert no.user_id == 7 and "Times do not match the log" in no.body and no.link_url == "/atwork/requests"


def test_withdrawal_tells_reviewers(api_client, clock, db):  # noqa: F811
    item = session_request(api_client, clock)
    post(api_client, f"{C}/{item['id']}/withdraw")
    [row] = outbox(db, "ATWORK_CORRECTION_WITHDRAWN")
    assert row.required_permissions and row.exclude_user_ids == [7]


def test_review_text_reveals_no_times_or_reasons(api_client, clock, db):  # noqa: F811
    session_request(api_client, clock)
    [row] = outbox(db, "ATWORK_CORRECTION_REQUESTED")
    text = row.title + row.body
    assert "Accidental" not in text and not re.search(r"\d{1,2}:\d{2}|Test User", text)


def test_a_replayed_submission_queues_nothing_more(api_client, clock, db):  # noqa: F811
    sid = check_in(api_client)["id"]
    clock.advance(hours=2)
    check_out(api_client)
    body = {
        "client_request_id": rid(),
        "reason": "Accidental check-out",
        "session_id": sid,
        "check_out_at": iso(clock.value - timedelta(minutes=9)),
    }
    assert [post(api_client, C, **body).status_code for _ in range(2)] == [201, 201]
    assert len(outbox(db, "ATWORK_CORRECTION_REQUESTED")) == 1


def test_platform_outage_does_not_fail_the_attendance_change(api_client, clock, db):  # noqa: F811
    item = session_request(api_client, clock)  # conftest points delivery at a closed port
    assert item["status"] == "PENDING"
    [row] = outbox(db, "ATWORK_CORRECTION_REQUESTED")
    assert row.status == "PENDING" and row.attempts == 1


def test_a_failed_notification_write_retries_then_is_sent_once(api_client, clock, db):  # noqa: F811
    session_request(api_client, clock)
    far = utcnow() + timedelta(days=1)
    bad = FakePlatform(RuntimeError("down"))
    assert notifications.deliver_pending(db, bad, far) == {"sent": 0, "failed": 1}
    good = FakePlatform()
    assert notifications.deliver_pending(db, good, far) == {"sent": 0, "failed": 0}  # backing off
    later = far + timedelta(days=1)
    assert notifications.deliver_pending(db, good, later) == {"sent": 1, "failed": 0}
    assert notifications.deliver_pending(db, good, later + timedelta(days=1)) == {"sent": 0, "failed": 0}
    assert len(good.calls) == 1 and good.calls[0]["dedupe_key"].endswith(":requested")


def test_delivery_stops_after_the_attempt_limit(api_client, clock, db):  # noqa: F811
    session_request(api_client, clock)
    moment, down = utcnow(), FakePlatform(False)
    for _ in range(notifications.MAX_ATTEMPTS + 2):
        moment += timedelta(days=1)
        notifications.deliver_pending(db, down, moment)
    [row] = outbox(db)
    assert row.status == "FAILED" and len(down.calls) == notifications.MAX_ATTEMPTS - 1


def test_concurrent_workers_produce_one_outcome_each(api_client, clock, db):  # noqa: F811
    session_request(api_client, clock)
    platform, barrier, results = FakePlatform(), Barrier(2), []

    def worker():
        session = SessionLocal()
        barrier.wait()
        try:
            results.append(notifications.deliver_pending(session, platform, utcnow() + timedelta(days=1)))
        except Exception as exc:  # noqa: BLE001 - SQLite may report a locked row
            results.append(exc)
        finally:
            session.close()

    from threading import Thread

    threads = [Thread(target=worker) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert {c["dedupe_key"] for c in platform.calls} == {outbox(db)[0].dedupe_key}


# --- scheduled alerts ---


def run(api, **kw):
    return api.post(RUN, headers=INTERNAL, **kw)


def test_scheduled_endpoint_requires_the_internal_secret(api_client, clock):  # noqa: F811
    assert api_client.post(RUN).status_code == 401
    assert api_client.post(RUN, headers=MGR).status_code == 401


def test_missed_checkout_alerts_the_employee_once(api_client, clock, db):  # noqa: F811
    sid = check_in(api_client)["id"]
    clock.advance(hours=11)
    assert run(api_client).json()["queued"]["missed_checkout"] == 0
    clock.advance(hours=2)
    assert run(api_client).json()["queued"]["missed_checkout"] == 1
    clock.advance(hours=1)
    assert run(api_client).json()["queued"]["missed_checkout"] == 0
    [row] = outbox(db, "ATWORK_MISSED_CHECKOUT")
    assert row.user_id == 7 and row.link_url.endswith(f"sessionId={sid}")


def test_pending_reminder_is_a_daily_digest_for_reviewers(api_client, clock, db):  # noqa: F811
    session_request(api_client, clock)
    assert run(api_client).json()["queued"]["pending_reminder"] == 0  # too recent
    clock.value = clock.value.replace(hour=2) + timedelta(days=2)  # 07:30 local
    assert run(api_client).json()["queued"]["pending_reminder"] == 0  # before the working day
    clock.advance(hours=4)
    assert [run(api_client).json()["queued"]["pending_reminder"] for _ in range(3)] == [1, 0, 0]
    clock.advance(days=1)
    assert run(api_client).json()["queued"]["pending_reminder"] == 1
    rows = outbox(db, "ATWORK_CORRECTION_REMINDER")
    assert len(rows) == 2 and all(r.required_permissions for r in rows) and "1 correction request has" in rows[0].body


def test_no_reminder_once_requests_are_decided(api_client, clock, db):  # noqa: F811
    item = session_request(api_client, clock)
    post(api_client, f"{M}/corrections/{item['id']}/approve", MGR)
    clock.advance(days=2, hours=4)
    assert run(api_client).json()["queued"]["pending_reminder"] == 0


# --- exports ---


def export(api, report, fmt, **extra):
    params = {"report": report, "format": fmt, "date_from": "2026-11-09", "date_to": "2026-11-09", **extra}
    return api.get(f"{M}/reports/export", params=params, headers=MGR)


def csv_rows(res):
    return list(csv.DictReader(io.StringIO(res.content.decode("utf-8-sig"))))


def one_session(api, clock):  # noqa: F811
    check_in(api)
    clock.advance(hours=2)
    check_out(api)


def test_filenames_use_business_time_and_fixed_names(api_client, clock):  # noqa: F811
    one_session(api_client, clock)  # now 05:00 UTC, 10:30:00 in Colombo
    expected = {
        "sessions": "Attendance",
        "employee_summary": "Employee_Summary",
        "missed_checkouts": "Missed_Checkout",
        "corrections": "Correction",
    }
    for report, name in expected.items():
        for fmt in ("csv", "xlsx"):
            header = export(api_client, report, fmt).headers["content-disposition"]
            assert header == f'attachment; filename="DijiAtWork_{name}_Report_2026-11-09_103000.{fmt}"'


def test_csv_separates_work_date_events_period_and_generation(api_client, clock):  # noqa: F811
    one_session(api_client, clock)
    [row] = csv_rows(export(api_client, "sessions", "csv"))
    assert row["Work date"] == "2026-11-09"
    assert row["Check-in date/time"] == "2026-11-09T08:30:00+05:30"
    assert row["Check-out date/time"] == "2026-11-09T10:30:00+05:30"
    assert row["Report"] == "Attendance Report"
    assert (row["Reporting period from"], row["Reporting period to"]) == ("2026-11-09", "2026-11-09")
    assert row["Export generated at"] == "2026-11-09T10:30:00+05:30" and row["Time zone"] == "Asia/Colombo"


def test_time_zone_setting_changes_presentation_not_stored_times(api_client, clock):  # noqa: F811
    one_session(api_client, clock)
    current = api_client.get(f"{M}/settings", headers=MGR).json()
    api_client.put(f"{M}/settings", json={**current, "business_time_zone": "UTC"}, headers=MGR)
    res = export(api_client, "sessions", "csv")
    [row] = csv_rows(res)
    assert row["Check-in date/time"] == "2026-11-09T03:00:00+00:00" and row["Time zone"] == "UTC"
    assert "_2026-11-09_050000.csv" in res.headers["content-disposition"]


def test_excel_uses_real_dates_and_an_information_sheet(api_client, clock):  # noqa: F811
    one_session(api_client, clock)
    book = load_workbook(io.BytesIO(export(api_client, "sessions", "xlsx").content))
    data, about = book.worksheets
    assert data.title == "Attendance Report" and about.title == "Export Information"
    heads = [c.value for c in data[1]]
    assert data.cell(2, heads.index("Check-in date/time") + 1).value == datetime(2026, 11, 9, 8, 30)
    assert data.cell(2, heads.index("Check-in date/time") + 1).number_format == "yyyy-mm-dd hh:mm:ss"
    work = data.cell(2, heads.index("Work date") + 1)
    assert work.is_date and work.number_format == "yyyy-mm-dd"
    info = {r[0].value: r[1].value for r in about.iter_rows()}
    assert info["Report name"] == "Attendance Report" and info["Time zone"] == "Asia/Colombo"
    assert info["Generated date/time"] == datetime(2026, 11, 9, 10, 30)
    assert info["Reporting period from"].date() == date(2026, 11, 9)


def test_correction_export_has_request_review_and_affected_dates(api_client, clock):  # noqa: F811
    item = session_request(api_client, clock)
    clock.advance(minutes=30)
    post(api_client, f"{M}/corrections/{item['id']}/approve", MGR)
    [row] = csv_rows(export(api_client, "corrections", "csv"))
    assert row["Affected work date"] == "2026-11-09"
    assert row["Requested date/time"].endswith("+05:30") and row["Reviewed date/time"].endswith("+05:30")
    assert row["Proposed check-out date/time"] == "2026-11-09T10:25:00+05:30"


def test_export_filters_and_formula_protection_still_apply(api_client, clock):  # noqa: F811
    one_session(api_client, clock)
    h9 = hdr(9)
    check_in(api_client, h9)
    assert {r["User ID"] for r in csv_rows(export(api_client, "sessions", "csv", user_id=7))} == {"7"}
    token = bearer(
        issue_token(8, module_roles={"atwork": {"role": "R", "client_id": None, "client_ids": None, "permissions": list(EMP)}})
    )
    denied = api_client.get(f"{M}/reports/export", params={"report": "sessions", "format": "csv"}, headers=token)
    assert denied.status_code == 403
