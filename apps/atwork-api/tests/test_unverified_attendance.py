"""Overdue and unverified attendance, and notification recovery after a cold start."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models.notifications import NotificationOutbox
from app.services import notifications
from app.services.time_accounting import daily_totals, is_unverified
from tests.test_corrections_management import MGR, A, C, M, clock, hdr, post, rid  # noqa: F401
from tests.test_uat_feedback import INTERNAL, FakePlatform, check_in, check_out, csv_rows, export, outbox, today

COLOMBO = ZoneInfo("Asia/Colombo")
H = 3600
LIMIT = 12 * H


@dataclass
class S:
    check_in_at: datetime
    check_out_at: datetime | None = None
    breaks: list = field(default_factory=list)
    correction_count: int = 0


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


# --- the rule ---


def test_normal_open_session_counts_live():
    now = at(9, 11)
    totals = daily_totals([S(at(9, 3))], COLOMBO, now, LIMIT)
    assert sum(t.gross_seconds for t in totals.values()) == 8 * H
    assert sum(t.provisional_seconds for t in totals.values()) == 0


def test_overdue_open_session_is_kept_as_provisional_not_lost():
    session, now = S(at(10, 7, 16)), at(12, 19, 38)
    totals = daily_totals([session], COLOMBO, now, LIMIT)
    assert is_unverified(session, now, LIMIT)
    assert sum(t.gross_seconds for t in totals.values()) == 0
    # Every second is preserved separately, still split at Colombo midnight.
    assert sum(t.provisional_seconds for t in totals.values()) == int((now - session.check_in_at).total_seconds())
    assert len(totals) == 4


def test_late_check_out_does_not_confirm_days_of_open_time():
    late = S(at(10, 7), check_out_at=at(12, 19))
    assert is_unverified(late, at(13, 0), LIMIT)
    assert sum(t.net_seconds for t in daily_totals([late], COLOMBO, at(13, 0), LIMIT).values()) == 0


def test_management_confirmed_session_counts_even_when_long():
    confirmed = S(at(10, 7), check_out_at=at(10, 21), correction_count=1)
    assert not is_unverified(confirmed, at(13, 0), LIMIT)
    assert sum(t.net_seconds for t in daily_totals([confirmed], COLOMBO, at(13, 0), LIMIT).values()) == 14 * H


def test_cross_midnight_session_within_the_threshold_is_unchanged():
    night = S(at(9, 16, 30), check_out_at=at(9, 21, 30))  # 22:00 to 03:00 Colombo
    totals = daily_totals([night], COLOMBO, at(10, 0), LIMIT)
    assert {d.isoformat(): t.net_seconds for d, t in totals.items()} == {"2026-11-09": 2 * H, "2026-11-10": 3 * H}
    assert daily_totals([night], COLOMBO, at(10, 0)) == totals  # same as before the rule


def test_a_session_exactly_at_the_threshold_still_counts():
    assert not is_unverified(S(at(9, 3), check_out_at=at(9, 15)), at(10, 0), LIMIT)


# --- through the API ---


def test_overdue_session_is_flagged_and_excluded_from_confirmed_totals(api_client, clock):  # noqa: F811
    sid = check_in(api_client)["id"]
    clock.advance(hours=13)
    status = api_client.get(f"{A}/status", headers=hdr()).json()
    assert status["session"]["unverified"] is True
    history = api_client.get(f"{A}/history", headers=hdr()).json()
    assert sum(d["net_seconds"] for d in history["daily_totals"]) == 0
    assert sum(d["provisional_seconds"] for d in history["daily_totals"]) == 13 * H
    assert api_client.get(f"{M}/employees/7/attendance", headers=MGR).json()["daily_totals"][0]["provisional_seconds"] > 0
    assert sid


def test_approved_correction_turns_provisional_time_into_confirmed_hours(api_client, clock):  # noqa: F811
    start = clock.value
    sid = check_in(api_client)["id"]
    clock.advance(hours=30)
    real_end = (start + timedelta(hours=8)).isoformat()
    made = post(api_client, C, client_request_id=rid(), reason="Forgot to check out", session_id=sid, check_out_at=real_end)
    assert made.status_code == 201
    assert post(api_client, f"{M}/corrections/{made.json()['id']}/approve", MGR).status_code == 200
    history = api_client.get(f"{A}/history", headers=hdr()).json()
    assert sum(d["net_seconds"] for d in history["daily_totals"]) == 8 * H
    assert sum(d["provisional_seconds"] for d in history["daily_totals"]) == 0


def test_rejected_correction_leaves_the_time_provisional(api_client, clock):  # noqa: F811
    sid = check_in(api_client)["id"]
    clock.advance(hours=20)
    check_out(api_client)
    made = post(
        api_client,
        C,
        client_request_id=rid(),
        reason="Forgot to check out",
        session_id=sid,
        check_out_at=(clock.value - timedelta(hours=12)).isoformat(),
    )
    post(api_client, f"{M}/corrections/{made.json()['id']}/reject", MGR, reason="Times do not match")
    history = api_client.get(f"{A}/history", headers=hdr()).json()
    assert sum(d["net_seconds"] for d in history["daily_totals"]) == 0
    assert sum(d["provisional_seconds"] for d in history["daily_totals"]) == 20 * H


def test_a_genuine_long_session_can_be_confirmed_unchanged(api_client, clock):  # noqa: F811
    sid = check_in(api_client)["id"]
    clock.advance(hours=13)
    check_out(api_client)
    made = post(api_client, C, client_request_id=rid(), reason="Long shift, times are correct", session_id=sid)
    assert made.status_code == 201
    post(api_client, f"{M}/corrections/{made.json()['id']}/approve", MGR)
    assert sum(d["net_seconds"] for d in api_client.get(f"{A}/history", headers=hdr()).json()["daily_totals"]) == 13 * H


def test_an_unchanged_request_is_still_refused_for_a_normal_session(api_client, clock):  # noqa: F811
    sid = check_in(api_client)["id"]
    clock.advance(hours=8)
    check_out(api_client)
    refused = post(api_client, C, client_request_id=rid(), reason="Nothing to change", session_id=sid)
    assert refused.status_code == 422 and "CORRECTION_NO_CHANGES" in refused.text


def test_today_counts_only_confirmed_time(api_client, clock):  # noqa: F811
    check_in(api_client)
    clock.advance(hours=13)
    totals = today(api_client)["totals"]
    assert totals["net_seconds"] == 0 and totals["provisional_seconds"] > 0


def test_exports_flag_unverified_time_and_keep_it_out_of_the_hours(api_client, clock):  # noqa: F811
    check_in(api_client)
    clock.advance(hours=13)
    [summary] = csv_rows(export(api_client, "employee_summary", "csv", date_to="2026-11-10"))
    assert summary["Net hours"] == "0.0" and float(summary["Unverified hours (not included)"]) == 13.0
    [row] = csv_rows(export(api_client, "sessions", "csv", date_to="2026-11-10"))
    assert row["Unverified"] == "Yes" and row["Net hours in period"] == "0.0"
    assert float(row["Unverified hours in period (not included)"]) == 13.0


# --- notifications ---


def test_delivery_waits_long_enough_for_a_cold_platform_core():
    assert notifications.DELIVERY_TIMEOUT_SECONDS >= 20
    assert notifications.platform_client()._timeout == notifications.DELIVERY_TIMEOUT_SECONDS


class ColdThenWarm(FakePlatform):
    def __init__(self, cold_calls):
        super().__init__()
        self.cold = cold_calls

    def deliver_notification(self, payload):
        self.calls.append(payload)
        if self.cold:
            self.cold -= 1
            raise TimeoutError("platform starting")
        return True


def _queue(db, count):
    for i in range(count):
        notifications.enqueue(db, f"test:{i}", "T", "t", "b", "/atwork", user_id=7)
    db.commit()


def test_recovers_after_platform_core_starts_and_sends_each_once(db):
    _queue(db, 2)
    platform, moment = ColdThenWarm(cold_calls=1), datetime.now(UTC) + timedelta(days=1)
    assert notifications.deliver_pending(db, platform, moment)["sent"] == 1  # first call times out
    moment += timedelta(days=1)
    assert notifications.deliver_pending(db, platform, moment)["sent"] == 1
    moment += timedelta(days=1)
    assert notifications.deliver_pending(db, platform, moment) == {"sent": 0, "failed": 0}
    keys = [c["dedupe_key"] for c in platform.calls]
    assert sorted(set(keys)) == ["test:0", "test:1"] and len(keys) == 3


def test_a_run_stops_early_while_platform_core_is_down(db):
    _queue(db, 6)
    down = FakePlatform(TimeoutError("down"))
    assert notifications.deliver_pending(db, down, datetime.now(UTC) + timedelta(days=1)) == {"sent": 0, "failed": 3}
    assert len(down.calls) == 3


def _fail(db, kind, key):
    db.add(
        NotificationOutbox(
            dedupe_key=key, kind=kind, title="t", body="b", link_url="/atwork", user_id=7, status="FAILED", attempts=12
        )
    )
    db.commit()


def test_failed_missed_checkout_is_retried_only_while_the_session_is_open(api_client, clock, db):  # noqa: F811
    open_id = check_in(api_client)["id"]
    _fail(db, "ATWORK_MISSED_CHECKOUT", f"atwork:missed-checkout:{open_id}")
    _fail(db, "ATWORK_MISSED_CHECKOUT", "atwork:missed-checkout:no-such-session")
    result = api_client.post("/api/atwork/internal/notifications/retry-failed", headers=INTERNAL).json()
    assert result == {"requeued": 1, "skipped": 1}
    statuses = {r.dedupe_key: r.status for r in outbox(db, "ATWORK_MISSED_CHECKOUT")}
    assert statuses[f"atwork:missed-checkout:{open_id}"] == "PENDING"
    assert statuses["atwork:missed-checkout:no-such-session"] == "FAILED"


def test_failed_review_request_is_not_resent_once_decided(api_client, clock, db):  # noqa: F811
    sid = check_in(api_client)["id"]
    clock.advance(hours=2)
    check_out(api_client)
    made = post(
        api_client,
        C,
        client_request_id=rid(),
        reason="Wrong time",
        session_id=sid,
        check_out_at=(clock.value - timedelta(minutes=5)).isoformat(),
    ).json()
    post(api_client, f"{M}/corrections/{made['id']}/approve", MGR)
    for row in outbox(db):
        row.status = "FAILED"
    db.commit()
    result = api_client.post("/api/atwork/internal/notifications/retry-failed", headers=INTERNAL).json()
    assert result == {"requeued": 1, "skipped": 1}  # the approval is still true; the review request is not
    assert {r.kind: r.status for r in outbox(db)}["ATWORK_CORRECTION_REQUESTED"] == "FAILED"


def test_retry_endpoint_requires_the_internal_secret(api_client):
    assert api_client.post("/api/atwork/internal/notifications/retry-failed").status_code == 401
    assert api_client.post("/api/atwork/internal/notifications/retry-failed", headers=MGR).status_code == 401
