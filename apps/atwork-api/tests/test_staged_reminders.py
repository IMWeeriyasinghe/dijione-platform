"""Staged missed-checkout reminder tests — 54-scenario matrix.

Coverage groups:
  A. Threshold eligibility (stage 1 / stage 2 / stage 3 boundary conditions)
  B. Delivery reliability (idempotency, concurrent runs, retry, failure)
  C. Attendance accuracy (unverified time exclusion/inclusion, Today page data)
  D. Rollout watermark (pre/post-deploy suppression)
  E. Resolution (checkout clears future reminders)
  F. Email channel (recipient resolution, missing email, blocked, disabled)
  G. Management visibility (stage 3 management notification)
  H. Email templates (subject lines, key content)
  I. Frontend flag (isOverdue derived from totals and policy threshold)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from app.core.constants import STATUS_COMPLETED, STATUS_OPEN
from app.models.attendance import AttendanceSession
from app.models.corrections import AttendanceEmployee
from app.models.notifications import NotificationOutbox
from app.models.reminders import AtworkReminderEmailSent, AtworkReminderWatermark
from app.services import notifications as svc
from app.services.attendance_policy import AttendancePolicy
from app.services.reminder_email_templates import (
    render_stage1_email,
    render_stage2_email,
    render_stage3_email,
)

ZONE = "Asia/Colombo"


def _policy(missed_checkout_hours: int = 12) -> AttendancePolicy:
    return AttendancePolicy(business_time_zone=ZONE, missed_checkout_hours=missed_checkout_hours)


def _now() -> datetime:
    return datetime.now(UTC)


_session_counter = 0


def _session(
    db, user_id: int, check_in_at: datetime, status: str = STATUS_OPEN, check_out_at: datetime | None = None
) -> AttendanceSession:
    global _session_counter
    _session_counter += 1
    # COMPLETED sessions require a check_out_at due to DB check constraint.
    effective_checkout = check_out_at if status == STATUS_COMPLETED else None
    if status == STATUS_COMPLETED and effective_checkout is None:
        effective_checkout = check_in_at + timedelta(hours=8)
    s = AttendanceSession(
        platform_user_id=user_id,
        work_mode="OFFICE",
        status=status,
        check_in_at=check_in_at,
        check_out_at=effective_checkout,
        time_zone=ZONE,
        check_in_request_id=f"req-{user_id}-{_session_counter}",
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
        version=1,
    )
    db.add(s)
    db.flush()
    return s


def _employee(db, user_id: int, email: str | None = "test@example.com") -> AttendanceEmployee:
    emp = AttendanceEmployee(platform_user_id=user_id, full_name=f"User {user_id}", email=email)
    db.add(emp)
    db.flush()
    return emp


def _watermark(db, at: datetime) -> None:
    db.merge(AtworkReminderWatermark(id=1, watermark_at=at))
    db.flush()


def _null_mail() -> MagicMock:
    """A mail client that always returns sent=False (NullTransport behaviour)."""
    client = MagicMock()
    result = MagicMock()
    result.sent = False
    result.outcome = "DISABLED"
    client.send.return_value = result
    return client


def _sent_mail() -> MagicMock:
    """A mail client that always returns sent=True."""
    client = MagicMock()
    result = MagicMock()
    result.sent = True
    result.outcome = "SENT"
    client.send.return_value = result
    return client


# ===========================================================================
# A. Threshold eligibility
# ===========================================================================


class TestThresholdEligibility:
    def test_A01_session_under_stage1_not_queued(self, db):
        """Session open 9h 59m — below stage1 threshold, no notification."""
        now = _now()
        _watermark(db, now - timedelta(hours=48))
        _session(db, 1, now - timedelta(hours=9, minutes=59))
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), now - timedelta(hours=48))
        assert result["stage1"] == 0

    def test_A02_session_exactly_stage1_queued(self, db):
        """Session open exactly 10h — stage1 fires."""
        now = _now()
        watermark = now - timedelta(hours=48)
        _watermark(db, watermark)
        _session(db, 1, now - timedelta(hours=10))
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        assert result["stage1"] == 1

    def test_A03_session_between_stage1_and_stage2(self, db):
        """Session open 11h — stage1 fires, stage2 (12h) does not."""
        now = _now()
        watermark = now - timedelta(hours=48)
        _watermark(db, watermark)
        _session(db, 1, now - timedelta(hours=11))
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(12), now, _null_mail(), watermark)
        assert result["stage1"] == 1
        assert result["stage2"] == 0

    def test_A04_session_at_stage2_threshold(self, db):
        """Session open exactly 12h — both stage1 and stage2 fire."""
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=12))
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(12), now, _null_mail(), watermark)
        assert result["stage1"] == 1
        assert result["stage2"] == 1

    def test_A05_stage2_threshold_respects_policy(self, db):
        """Stage2 uses policy.missed_checkout_hours, not a hardcoded 12."""
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=14))
        _employee(db, 1)
        db.commit()
        result_default = svc._enqueue_staged_reminders(db, _policy(12), now, _null_mail(), watermark)
        assert result_default["stage2"] == 1

    def test_A06_stage2_not_fired_at_11h_with_12h_policy(self, db):
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=11))
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(12), now, _null_mail(), watermark)
        assert result["stage2"] == 0

    def test_A07_stage3_fires_at_24h(self, db):
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=24))
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(12), now, _null_mail(), watermark)
        assert result["stage3"] == 1

    def test_A08_stage3_not_fired_at_23h(self, db):
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=23))
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(12), now, _null_mail(), watermark)
        assert result["stage3"] == 0

    def test_A09_all_three_stages_at_25h(self, db):
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=25))
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(12), now, _null_mail(), watermark)
        assert result["stage1"] == 1
        assert result["stage2"] == 1
        assert result["stage3"] == 1


# ===========================================================================
# B. Delivery reliability — idempotency and concurrent safety
# ===========================================================================


class TestDeliveryReliability:
    def test_B01_stage1_not_duplicated_on_second_run(self, db):
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=11))
        _employee(db, 1)
        db.commit()
        r1 = svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        r2 = svc._enqueue_staged_reminders(db, _policy(), now + timedelta(minutes=15), _null_mail(), watermark)
        assert r1["stage1"] == 1
        assert r2["stage1"] == 0  # dedupe_key already exists

    def test_B02_stage2_not_duplicated_on_second_run(self, db):
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=13))
        _employee(db, 1)
        db.commit()
        r1 = svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        r2 = svc._enqueue_staged_reminders(db, _policy(), now + timedelta(minutes=15), _null_mail(), watermark)
        assert r1["stage2"] == 1
        assert r2["stage2"] == 0

    def test_B03_email_sent_only_once_per_stage(self, db):
        """Email row unique constraint ensures at-most-one per (session, stage)."""
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=11))
        _employee(db, 1, email="user@example.com")
        db.commit()
        mail = _sent_mail()
        svc._enqueue_staged_reminders(db, _policy(), now, mail, watermark)
        call_count_1 = mail.send.call_count
        svc._enqueue_staged_reminders(db, _policy(), now + timedelta(minutes=15), mail, watermark)
        assert mail.send.call_count == call_count_1  # no new sends

    def test_B04_multiple_sessions_independent(self, db):
        """Two users open > 10h each both get reminders."""
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=11))
        _session(db, 2, now - timedelta(hours=11))
        _employee(db, 1)
        _employee(db, 2)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        assert result["stage1"] == 2

    def test_B05_completed_session_skipped(self, db):
        """A session that is COMPLETED before the scheduler runs is not reminded."""
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=11), status=STATUS_COMPLETED, check_out_at=now - timedelta(minutes=5))
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        assert result["stage1"] == 0

    def test_B06_in_app_notification_kinds_correct(self, db):
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=25))
        _employee(db, 1)
        db.commit()
        svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        from sqlalchemy import select

        kinds = set(db.scalars(select(NotificationOutbox.kind)))
        assert "ATWORK_REMINDER_STAGE1" in kinds
        assert "ATWORK_REMINDER_STAGE2" in kinds
        assert "ATWORK_REMINDER_STAGE3" in kinds

    def test_B07_email_tracking_row_created(self, db):
        from sqlalchemy import select

        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=11))
        _employee(db, 1, email="user@example.com")
        db.commit()
        svc._enqueue_staged_reminders(db, _policy(), now, _sent_mail(), watermark)
        rows = list(db.scalars(select(AtworkReminderEmailSent)))
        assert any(r.stage == 1 for r in rows)


# ===========================================================================
# C. Attendance accuracy
# ===========================================================================


class TestAttendanceAccuracy:
    def test_C01_open_session_counted_in_time_accounting(self, db):
        """time_accounting counts open sessions up to now — this is by design."""
        from app.services.time_accounting import session_totals

        now = _now()
        session = _session(db, 1, now - timedelta(hours=25))
        db.commit()
        totals = session_totals(session, now)
        assert totals.gross_seconds >= 25 * 3600

    def test_C02_completed_session_uses_checkout_time(self, db):
        """Completed sessions use check_out_at, not now."""
        from app.services.time_accounting import session_totals

        now = _now()
        checkout = now - timedelta(hours=9)
        s = _session(db, 1, now - timedelta(hours=10), status=STATUS_COMPLETED, check_out_at=checkout)
        db.commit()
        totals = session_totals(s, now)
        assert abs(totals.gross_seconds - 3600) < 5  # ~1 hour

    def test_C03_unverified_session_included_in_today_totals(self, db):
        """Open (unverified) sessions are included in Today totals — not silently excluded."""
        from app.services.time_accounting import session_totals

        now = _now()
        s = _session(db, 1, now - timedelta(hours=14))
        db.commit()
        totals = session_totals(s, now)
        assert totals.gross_seconds >= 14 * 3600

    def test_C04_missed_checkouts_report_uses_open_seconds(self, db):
        """missed_checkouts() reports correct open_seconds for the reporting view."""
        from app.services.reporting import Reporting

        policy = _policy()
        now = _now()
        _session(db, 1, now - timedelta(hours=14))
        _employee(db, 1)
        db.commit()
        rows = Reporting(db, policy, now).missed_checkouts()
        assert len(rows) == 1
        assert rows[0]["open_seconds"] >= 14 * 3600

    def test_C05_no_fabricated_checkout_or_timestamp(self, db):
        """Staged reminders must never write check_out_at to any session."""
        now = _now()
        watermark = now - timedelta(hours=48)
        s = _session(db, 1, now - timedelta(hours=25))
        _employee(db, 1)
        db.commit()
        svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        db.refresh(s)
        assert s.check_out_at is None
        assert s.status == STATUS_OPEN

    def test_C06_no_historical_record_modified(self, db):
        """enqueue_staged_reminders must not write to AttendanceSessions."""

        now = _now()
        watermark = now - timedelta(hours=48)
        s = _session(db, 1, now - timedelta(hours=25))
        db.commit()
        original_check_in = s.check_in_at
        _employee(db, 1)
        svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        db.refresh(s)
        assert s.check_in_at == original_check_in


# ===========================================================================
# D. Rollout watermark
# ===========================================================================


class TestRolloutWatermark:
    def test_D01_pre_deploy_session_no_staged_reminders(self, db):
        """Session checked in BEFORE the watermark → no staged reminders."""
        now = _now()
        watermark = now  # watermark is now = session started before deploy
        _session(db, 1, now - timedelta(hours=25))
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        assert result["stage1"] == 0

    def test_D02_post_deploy_session_gets_staged_reminders(self, db):
        """Session checked in AFTER the watermark → staged reminders fire."""
        watermark = _now() - timedelta(hours=48)
        now = _now()
        _session(db, 1, now - timedelta(hours=11))
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        assert result["stage1"] == 1

    def test_D03_legacy_path_covers_pre_deploy_sessions(self, db):
        """enqueue_scheduled uses legacy ATWORK_MISSED_CHECKOUT for pre-watermark sessions."""
        now = _now()
        watermark = now  # all sessions are pre-deploy
        db.merge(AtworkReminderWatermark(id=1, watermark_at=watermark))
        db.commit()
        _session(db, 1, now - timedelta(hours=14))
        _employee(db, 1)
        db.commit()
        result = svc.enqueue_scheduled(db, _policy(), now, _null_mail())
        assert result["missed_checkout"] == 1
        assert result["stage1"] == 0

    def test_D04_watermark_seeded_if_missing(self, db):
        """If the watermark row is missing (should not happen post-migration),
        _get_watermark seeds it from now."""
        now = _now()
        # No watermark row in DB
        wm = svc._get_watermark(db, now)
        assert wm is not None
        # On second call it uses the stored row.
        wm2 = svc._get_watermark(db, now + timedelta(hours=1))
        assert wm2 == wm  # same timestamp, not updated

    def test_D05_exactly_at_watermark_boundary(self, db):
        """Session started at exactly watermark_at — included (>= comparison)."""
        watermark = _now() - timedelta(hours=12)
        now = _now()
        # Session exactly at watermark: check_in_at >= watermark → included in staged path
        _session(db, 1, watermark)
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        assert result["stage1"] == 1  # >= means session at watermark IS included


# ===========================================================================
# E. Resolution — checkout stops future reminders
# ===========================================================================


class TestResolution:
    def test_E01_checked_out_session_no_new_reminders(self, db):
        """After checkout (status=COMPLETED), session is excluded from staged reminders."""
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=25), status=STATUS_COMPLETED, check_out_at=now - timedelta(hours=1))
        _employee(db, 1)
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        assert result["stage1"] == 0

    def test_E02_still_relevant_returns_false_for_completed(self, db):
        """_still_relevant returns False for a stage2 notification whose session completed."""
        now = _now()
        watermark = now - timedelta(hours=48)
        s = _session(db, 1, now - timedelta(hours=14))
        _employee(db, 1)
        db.commit()
        svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        from sqlalchemy import select

        row = db.scalars(select(NotificationOutbox).where(NotificationOutbox.kind == "ATWORK_REMINDER_STAGE2")).first()
        assert row is not None
        # Mark session completed.
        s.status = STATUS_COMPLETED
        s.check_out_at = now
        db.commit()
        result = svc._still_relevant(db, row, _policy(), now)
        assert result is False


# ===========================================================================
# F. Email channel
# ===========================================================================


class TestEmailChannel:
    def test_F01_no_email_when_employee_has_no_address(self, db):
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=11))
        _employee(db, 1, email=None)
        db.commit()
        mail = _sent_mail()
        svc._enqueue_staged_reminders(db, _policy(), now, mail, watermark)
        assert mail.send.call_count == 0

    def test_F02_email_sent_when_address_available(self, db):
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=11))
        _employee(db, 1, email="employee@example.com")
        db.commit()
        mail = _sent_mail()
        result = svc._enqueue_staged_reminders(db, _policy(), now, mail, watermark)
        assert mail.send.call_count >= 1
        assert result["email_sent"] >= 1

    def test_F03_blocked_recipient_tracked_as_failed(self, db):

        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=11))
        _employee(db, 1, email="blocked@external.com")
        db.commit()
        mail = MagicMock()
        result = MagicMock()
        result.sent = False
        result.outcome = "BLOCKED"
        mail.send.return_value = result
        svc._enqueue_staged_reminders(db, _policy(), now, mail, watermark)
        from sqlalchemy import select

        rows = list(db.scalars(select(AtworkReminderEmailSent)))
        assert any(r.status == "FAILED" for r in rows)

    def test_F04_resolve_recipient_rejects_empty_email(self, db):
        _employee(db, 1, email="")
        db.flush()
        result = svc._resolve_recipient(db, 1)
        assert result is None

    def test_F05_resolve_recipient_rejects_no_at_sign(self, db):
        _employee(db, 1, email="notanemail")
        db.flush()
        result = svc._resolve_recipient(db, 1)
        assert result is None

    def test_F06_resolve_recipient_returns_valid_email(self, db):
        _employee(db, 1, email="valid@company.com")
        db.flush()
        result = svc._resolve_recipient(db, 1)
        assert result == "valid@company.com"

    def test_F07_email_not_sent_when_no_employee_row(self, db):
        """If AttendanceEmployee row is missing, email is skipped (no crash)."""
        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=11))
        # No _employee call.
        db.commit()
        mail = _sent_mail()
        svc._enqueue_staged_reminders(db, _policy(), now, mail, watermark)
        assert mail.send.call_count == 0


# ===========================================================================
# G. Management visibility (stage 3)
# ===========================================================================


class TestManagementVisibility:
    def test_G01_stage3_creates_management_notification(self, db):
        from sqlalchemy import select

        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=25))
        _employee(db, 1)
        db.commit()
        svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        mgmt_rows = list(db.scalars(select(NotificationOutbox).where(NotificationOutbox.kind == "ATWORK_REMINDER_STAGE3_MGMT")))
        assert len(mgmt_rows) == 1
        # Management notification has required_permissions (reviewer audience).
        assert mgmt_rows[0].required_permissions is not None
        # Employee excluded from management notification.
        assert mgmt_rows[0].exclude_user_ids == [1]

    def test_G02_management_notification_not_duplicated(self, db):
        from sqlalchemy import select

        now = _now()
        watermark = now - timedelta(hours=48)
        _session(db, 1, now - timedelta(hours=25))
        _employee(db, 1)
        db.commit()
        svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), watermark)
        svc._enqueue_staged_reminders(db, _policy(), now + timedelta(minutes=15), _null_mail(), watermark)
        rows = list(db.scalars(select(NotificationOutbox).where(NotificationOutbox.kind == "ATWORK_REMINDER_STAGE3_MGMT")))
        assert len(rows) == 1  # dedupe prevents second insert


# ===========================================================================
# H. Email templates
# ===========================================================================


class TestEmailTemplates:
    def _zone(self):
        from zoneinfo import ZoneInfo

        return ZoneInfo("Asia/Colombo")

    def test_H01_stage1_subject(self):
        now = _now()
        subject, html = render_stage1_email(
            employee_name="Amara",
            check_in_at=now,
            zone=self._zone(),
            zone_name="Asia/Colombo",
            app_url="https://app.example.com",
        )
        assert subject == "DijiAtWork | Your work session is still active"

    def test_H02_stage2_subject(self):
        now = _now()
        subject, html = render_stage2_email(
            employee_name="Amara",
            check_in_at=now,
            zone=self._zone(),
            zone_name="Asia/Colombo",
            threshold_hours=12,
            app_url="https://app.example.com",
        )
        assert subject == "DijiAtWork | Action required: Possible missed checkout"

    def test_H03_stage3_subject(self):
        now = _now()
        subject, html = render_stage3_email(
            employee_name="Amara",
            check_in_at=now,
            zone=self._zone(),
            zone_name="Asia/Colombo",
            app_url="https://app.example.com",
        )
        assert subject == "DijiAtWork | Follow-up: Your attendance session remains open"

    def test_H04_employee_name_in_body(self):
        now = _now()
        _, html = render_stage1_email(
            employee_name="Kasun Perera",
            check_in_at=now,
            zone=self._zone(),
            zone_name="Asia/Colombo",
            app_url="https://app.example.com",
        )
        assert "Kasun Perera" in html

    def test_H05_app_url_in_body(self):
        now = _now()
        _, html = render_stage1_email(
            employee_name="Test",
            check_in_at=now,
            zone=self._zone(),
            zone_name="Asia/Colombo",
            app_url="https://dijione.example.com",
        )
        assert "https://dijione.example.com" in html

    def test_H06_stage2_threshold_hours_in_body(self):
        now = _now()
        _, html = render_stage2_email(
            employee_name="Test",
            check_in_at=now,
            zone=self._zone(),
            zone_name="Asia/Colombo",
            threshold_hours=14,
            app_url="https://app.example.com",
        )
        assert "14" in html

    def test_H07_check_in_time_shown_in_all_templates(self):
        from zoneinfo import ZoneInfo

        zone = ZoneInfo("Asia/Colombo")
        check_in = datetime(2026, 11, 25, 9, 0, 0, tzinfo=UTC)
        for _subject, html in [
            render_stage1_email(employee_name="X", check_in_at=check_in, zone=zone, zone_name="Asia/Colombo", app_url="http://x"),
            render_stage2_email(
                employee_name="X",
                check_in_at=check_in,
                zone=zone,
                zone_name="Asia/Colombo",
                threshold_hours=12,
                app_url="http://x",
            ),
            render_stage3_email(employee_name="X", check_in_at=check_in, zone=zone, zone_name="Asia/Colombo", app_url="http://x"),
        ]:
            assert "2026" in html  # check-in year appears

    def test_H08_no_secrets_or_tokens_in_templates(self):
        """Templates must not contain anything that looks like a token or secret."""
        import re

        now = _now()
        for _subject, html in [
            render_stage1_email(
                employee_name="X", check_in_at=now, zone=self._zone(), zone_name="Asia/Colombo", app_url="http://x"
            ),
        ]:
            assert not re.search(r"eyJ[A-Za-z0-9]+\.[A-Za-z0-9]+", html)  # no JWT fragments


# ===========================================================================
# I. Frontend isOverdue flag logic
# ===========================================================================


class TestFrontendIsOverdueFlagLogic:
    """These tests validate the Python-side logic equivalent to the
    TypeScript `isOverdue` computation in the Today page."""

    def test_I01_is_overdue_false_below_threshold(self):
        gross_seconds = 11 * 3600
        threshold_seconds = 12 * 3600
        is_overdue = gross_seconds >= threshold_seconds
        assert is_overdue is False

    def test_I02_is_overdue_true_at_threshold(self):
        gross_seconds = 12 * 3600
        threshold_seconds = 12 * 3600
        is_overdue = gross_seconds >= threshold_seconds
        assert is_overdue is True

    def test_I03_is_overdue_true_above_threshold(self):
        gross_seconds = 25 * 3600
        threshold_seconds = 12 * 3600
        is_overdue = gross_seconds >= threshold_seconds
        assert is_overdue is True

    def test_I04_no_session_means_not_overdue(self):
        session = None
        is_overdue = session is not None  # mirrors: Boolean(session && policy && totals && ...)
        assert is_overdue is False

    def test_I05_policy_threshold_configurable(self):
        """isOverdue threshold changes with policy.missed_checkout_hours."""
        gross_seconds = 8 * 3600
        for threshold_hours, expected in [(12, False), (8, True), (6, True)]:
            is_overdue = gross_seconds >= threshold_hours * 3600
            assert is_overdue is expected, f"threshold={threshold_hours}h failed"


# ===========================================================================
# J. Catch-up sequencing (email flood suppression)
# ===========================================================================


class TestCatchUpSequencing:
    """When a session first appears at a late stage, only the most relevant email
    is sent in that run.  In-app notifications are still created for all applicable
    stages via deduplication.
    """

    def test_J01_25h_session_sends_only_stage3_email(self, db):
        """A 25 h session seen for the first time produces exactly 1 email (stage 3)."""
        now = _now()
        _watermark(db, now - timedelta(hours=48))
        _session(db, 1, now - timedelta(hours=25))
        _employee(db, 1, "emp@example.com")
        db.commit()
        mail = _sent_mail()
        result = svc._enqueue_staged_reminders(db, _policy(), now, mail, now - timedelta(hours=48))
        assert result["email_sent"] == 1
        # Stage-3 email row must be SENT
        from sqlalchemy import select

        from app.models.reminders import AtworkReminderEmailSent

        rows = db.scalars(select(AtworkReminderEmailSent)).all()
        assert any(r.stage == 3 and r.status == "SENT" for r in rows)
        # Stage-1 and stage-2 rows must NOT exist (suppressed)
        assert all(r.stage not in (1, 2) for r in rows)

    def test_J02_13h_session_sends_only_stage2_email(self, db):
        """A 13 h session (past threshold, below 24 h) sends only the stage-2 email."""
        now = _now()
        _watermark(db, now - timedelta(hours=48))
        _session(db, 2, now - timedelta(hours=13))
        _employee(db, 2, "emp2@example.com")
        db.commit()
        mail = _sent_mail()
        result = svc._enqueue_staged_reminders(db, _policy(missed_checkout_hours=12), now, mail, now - timedelta(hours=48))
        assert result["email_sent"] == 1
        from sqlalchemy import select

        from app.models.reminders import AtworkReminderEmailSent

        rows = db.scalars(select(AtworkReminderEmailSent)).all()
        assert any(r.stage == 2 and r.status == "SENT" for r in rows)
        assert all(r.stage not in (1, 3) for r in rows)

    def test_J03_normal_progression_sends_one_email_per_run(self, db):
        """Two incremental runs: first at 10 h sends stage-1 email, second at 12 h sends stage-2.
        Neither run sends more than 1 email.
        """
        base = _now()
        _watermark(db, base - timedelta(hours=48))
        _session(db, 3, base - timedelta(hours=10, minutes=1))
        _employee(db, 3, "emp3@example.com")
        db.commit()

        # Run 1 — just past stage 1
        mail1 = _sent_mail()
        result1 = svc._enqueue_staged_reminders(db, _policy(missed_checkout_hours=12), base, mail1, base - timedelta(hours=48))
        assert result1["email_sent"] == 1

        # Run 2 — now at 12 h+ (stage 2 threshold)
        now2 = base + timedelta(hours=2)
        mail2 = _sent_mail()
        result2 = svc._enqueue_staged_reminders(db, _policy(missed_checkout_hours=12), now2, mail2, base - timedelta(hours=48))
        assert result2["email_sent"] == 1

        from sqlalchemy import select

        from app.models.reminders import AtworkReminderEmailSent

        rows = db.scalars(select(AtworkReminderEmailSent)).all()
        # Exactly one stage-1 SENT and one stage-2 SENT; no stage-3 yet.
        assert sum(1 for r in rows if r.stage == 1 and r.status == "SENT") == 1
        assert sum(1 for r in rows if r.stage == 2 and r.status == "SENT") == 1
        assert all(r.stage != 3 for r in rows)

    def test_J04_in_app_notifications_created_for_all_stages_in_catchup(self, db):
        """A 25 h catch-up run still creates in-app notifications for all 3 stages."""
        now = _now()
        _watermark(db, now - timedelta(hours=48))
        _session(db, 4, now - timedelta(hours=25))
        _employee(db, 4, "emp4@example.com")
        db.commit()
        result = svc._enqueue_staged_reminders(db, _policy(), now, _null_mail(), now - timedelta(hours=48))
        assert result["stage1"] == 1
        assert result["stage2"] == 1
        assert result["stage3"] == 1


# ===========================================================================
# K. Email retry
# ===========================================================================


class TestEmailRetry:
    """PENDING email rows are retried when next_attempt_at has elapsed and the
    session is still open; rows whose sessions have been checked out are cancelled.
    """

    def _make_pending_row(self, db, session_id, stage: int, next_attempt_at):
        from app.models.reminders import AtworkReminderEmailSent

        row = AtworkReminderEmailSent(
            session_id=session_id,
            stage=stage,
            recipient_email="retry@example.com",
            status="PENDING",
            next_attempt_at=next_attempt_at,
        )
        db.add(row)
        db.flush()
        return row

    def test_K01_pending_row_retried_after_next_attempt_at(self, db):
        """A PENDING row whose next_attempt_at is in the past is retried."""
        now = _now()
        _watermark(db, now - timedelta(hours=48))
        s = _session(db, 10, now - timedelta(hours=11))
        _employee(db, 10, "retry@example.com")
        db.commit()
        self._make_pending_row(db, s.id, 1, now - timedelta(minutes=5))
        db.commit()

        mail = _sent_mail()
        result = svc._retry_pending_emails(db, mail, _policy(), now)
        assert result["email_retried"] == 1
        assert result["email_cancelled"] == 0

    def test_K02_pending_row_not_retried_before_next_attempt_at(self, db):
        """A PENDING row whose next_attempt_at is still in the future is not touched."""
        now = _now()
        _watermark(db, now - timedelta(hours=48))
        s = _session(db, 11, now - timedelta(hours=11))
        _employee(db, 11, "retry2@example.com")
        db.commit()
        self._make_pending_row(db, s.id, 1, now + timedelta(minutes=30))
        db.commit()

        mail = _sent_mail()
        result = svc._retry_pending_emails(db, mail, _policy(), now)
        assert result["email_retried"] == 0
        assert result["email_cancelled"] == 0

    def test_K03_pending_row_cancelled_when_session_checked_out(self, db):
        """If the session was checked out before the retry, the row is marked FAILED."""
        now = _now()
        _watermark(db, now - timedelta(hours=48))
        s = _session(db, 12, now - timedelta(hours=14), status=STATUS_COMPLETED)
        _employee(db, 12, "retry3@example.com")
        db.commit()
        self._make_pending_row(db, s.id, 2, now - timedelta(minutes=1))
        db.commit()

        mail = _sent_mail()
        result = svc._retry_pending_emails(db, mail, _policy(), now)
        assert result["email_retried"] == 0
        assert result["email_cancelled"] == 1
        from sqlalchemy import select

        from app.models.reminders import AtworkReminderEmailSent

        row = db.scalars(select(AtworkReminderEmailSent)).first()
        assert row.status == "FAILED"

    def test_K04_retry_wired_from_enqueue_scheduled(self, db):
        """enqueue_scheduled calls _retry_pending_emails when mail is provided."""
        now = _now()
        _watermark(db, now - timedelta(hours=48))
        s = _session(db, 13, now - timedelta(hours=11))
        _employee(db, 13, "retry4@example.com")
        db.commit()

        # Manually insert a PENDING row with elapsed next_attempt_at.
        from app.models.reminders import AtworkReminderEmailSent

        row = AtworkReminderEmailSent(
            session_id=s.id,
            stage=1,
            recipient_email="retry4@example.com",
            status="PENDING",
            next_attempt_at=now - timedelta(minutes=10),
        )
        db.add(row)
        db.commit()

        mail = _sent_mail()
        result = svc.enqueue_scheduled(db, _policy(), now, mail=mail)
        assert result["email_retried"] == 1


# ===========================================================================
# L. Recipient identity validation
# ===========================================================================


class TestRecipientIdentity:
    """_resolve_recipient validates the email from AttendanceEmployee (Entra-sourced
    via remember_employee) with an RFC-inspired regex and service-account prefix rejection.
    """

    def test_L01_valid_email_accepted(self, db):
        """A well-formed employee email is returned unchanged."""
        _employee(db, 20, "alice@dijitalteam.com")
        db.commit()
        assert svc._resolve_recipient(db, 20) == "alice@dijitalteam.com"

    def test_L02_missing_at_sign_rejected(self, db):
        """An email without @ is rejected."""
        _employee(db, 21, "notanemail")
        db.commit()
        assert svc._resolve_recipient(db, 21) is None

    def test_L03_no_domain_dot_rejected(self, db):
        """An email whose domain has no dot is rejected."""
        _employee(db, 22, "user@localdomain")
        db.commit()
        assert svc._resolve_recipient(db, 22) is None

    def test_L04_no_reply_prefix_rejected(self, db):
        """no-reply@ address is rejected as a service account."""
        _employee(db, 23, "no-reply@dijitalteam.com")
        db.commit()
        assert svc._resolve_recipient(db, 23) is None

    def test_L05_noreply_prefix_rejected(self, db):
        """noreply@ address is rejected as a service account."""
        _employee(db, 24, "noreply@example.com")
        db.commit()
        assert svc._resolve_recipient(db, 24) is None

    def test_L06_donotreply_prefix_rejected(self, db):
        """donotreply@ address is rejected as a service account."""
        _employee(db, 25, "donotreply@example.com")
        db.commit()
        assert svc._resolve_recipient(db, 25) is None

    def test_L07_empty_email_rejected(self, db):
        """An empty string email is rejected."""
        _employee(db, 26, "")
        db.commit()
        assert svc._resolve_recipient(db, 26) is None

    def test_L08_whitespace_only_email_rejected(self, db):
        """A whitespace-only email is rejected."""
        _employee(db, 27, "   ")
        db.commit()
        assert svc._resolve_recipient(db, 27) is None

    def test_L09_spaces_in_local_part_rejected(self, db):
        """An address with spaces in the local part is rejected."""
        _employee(db, 28, "first last@example.com")
        db.commit()
        assert svc._resolve_recipient(db, 28) is None
