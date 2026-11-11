"""A sync run must neither block later runs nor overstate what it read."""

import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from app.models.sync_run import RecruitmentSyncRun, SyncStatus, SyncTriggerType
from app.services import recruitment_sync_service as module
from app.services.recruitment_sync_service import RecruitmentSyncService


def _stuck(db, age: timedelta) -> RecruitmentSyncRun:
    run = RecruitmentSyncRun(
        run_id=f"run-{age.seconds}", provider="LEVER", trigger_type=SyncTriggerType.SCHEDULED.value,
        requested_by_application="test", correlation_id="c", status=SyncStatus.RUNNING.value,
        started_at=datetime.now(UTC) - age, updated_at=datetime.now(UTC) - age,
    )
    db.add(run)
    db.commit()
    return run


def _request(db):
    return RecruitmentSyncService(db).request_sync(
        trigger_type=SyncTriggerType.SCHEDULED, requested_by_application="test"
    )


def test_abandoned_run_no_longer_blocks_a_new_sync(db):
    stuck = _stuck(db, timedelta(hours=2))
    new, created = _request(db)
    assert created and new.run_id != stuck.run_id
    db.refresh(stuck)
    assert stuck.status == SyncStatus.FAILED.value and "Abandoned" in stuck.error_summary


def test_a_recent_run_still_blocks(db):
    running = _stuck(db, timedelta(minutes=5))
    existing, created = _request(db)
    assert not created and existing.run_id == running.run_id


def _execute(db, monkeypatch, opportunities):
    run, _ = _request(db)
    run_id = run.run_id
    sent = []
    monkeypatch.setattr(module, "SessionLocal", lambda: db)
    monkeypatch.setattr(module.LeverPostingSyncService, "sync_postings", lambda self: {"total": 1})
    monkeypatch.setattr(module.LeverCandidacySyncService, "sync_opportunities", lambda self, limit: opportunities)
    monkeypatch.setattr(module.platform_notify, "notify_module_role", lambda **kw: sent.append(kw))
    RecruitmentSyncService.execute_run(run_id)
    return RecruitmentSyncService(db).get(run_id), sent


def test_unread_client_postings_make_the_run_partial(db, monkeypatch):
    run, sent = _execute(db, monkeypatch, {"dtc_postings_read": 3, "dtc_postings_total": 5})
    assert run.status == SyncStatus.PARTIAL.value
    assert run.error_summary == "Incomplete: 3 of 5 client postings read."
    assert len(sent) == 1


def test_complete_read_succeeds_silently_even_past_the_recent_cap(db, monkeypatch):
    run, sent = _execute(
        db, monkeypatch, {"dtc_postings_read": 5, "dtc_postings_total": 5, "opportunity_limit_reached": True}
    )
    assert run.status == SyncStatus.SUCCEEDED.value and run.error_summary is None
    assert sent == []


def test_a_slow_run_with_a_heartbeat_is_never_abandoned(db, monkeypatch):
    factory = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr(module, "SessionLocal", factory)
    monkeypatch.setattr(module, "_HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(module, "_ABANDONED_AFTER", timedelta(seconds=0.4))
    monkeypatch.setattr(module.LeverPostingSyncService, "sync_postings", lambda self: {})
    overlapped = []

    def slow(self, limit):
        for _ in range(8):
            time.sleep(0.1)
            other = factory()
            try:
                overlapped.append(RecruitmentSyncService(other).request_sync(
                    trigger_type=SyncTriggerType.SCHEDULED, requested_by_application="other"
                )[1])
            finally:
                other.close()
        return {}

    monkeypatch.setattr(module.LeverCandidacySyncService, "sync_opportunities", slow)
    run, _ = _request(db)
    run_id = run.run_id
    RecruitmentSyncService.execute_run(run_id)

    assert overlapped == [False] * 8
    db.expire_all()
    assert RecruitmentSyncService(db).get(run_id).status == SyncStatus.SUCCEEDED.value


def test_a_killed_replica_stops_the_heartbeat_and_the_run_is_recovered(db, monkeypatch):
    monkeypatch.setattr(module, "_ABANDONED_AFTER", timedelta(seconds=0.05))
    stuck = _stuck(db, timedelta(0))
    time.sleep(0.1)
    new_run, created = _request(db)
    assert created and new_run.run_id != stuck.run_id


def test_a_run_finishing_after_abandonment_does_not_overwrite_the_record(db, monkeypatch):
    def abandon(self, limit):
        row = db.query(RecruitmentSyncRun).one()
        row.status, row.error_summary = SyncStatus.FAILED.value, "Abandoned"
        db.commit()
        return {}

    monkeypatch.setattr(module.LeverCandidacySyncService, "sync_opportunities", abandon)
    monkeypatch.setattr(module, "SessionLocal", lambda: db)
    monkeypatch.setattr(module.LeverPostingSyncService, "sync_postings", lambda self: {})
    sent = []
    monkeypatch.setattr(module.platform_notify, "notify_module_role", lambda **kw: sent.append(kw))
    run, _ = _request(db)
    run_id = run.run_id
    RecruitmentSyncService.execute_run(run_id)
    row = RecruitmentSyncService(db).get(run_id)
    assert (row.status, row.error_summary) == (SyncStatus.FAILED.value, "Abandoned") and sent == []


def test_failure_during_the_read_is_failed_not_partial(db, monkeypatch):
    def boom(self, limit):
        raise RuntimeError("source down")

    monkeypatch.setattr(module.LeverCandidacySyncService, "sync_opportunities", boom)
    monkeypatch.setattr(module, "SessionLocal", lambda: db)
    monkeypatch.setattr(module.LeverPostingSyncService, "sync_postings", lambda self: {})
    monkeypatch.setattr(module.platform_notify, "notify_module_role", lambda **kw: None)
    run, _ = _request(db)
    run_id = run.run_id
    RecruitmentSyncService.execute_run(run_id)
    assert RecruitmentSyncService(db).get(run_id).status == SyncStatus.FAILED.value


def test_postgres_takes_the_single_flight_lock_before_checking(monkeypatch):
    statements = []

    class Session:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, statement, params=None):
            statements.append(str(statement))
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [_active()]))

        def commit(self):
            statements.append("COMMIT")

    def _active():
        return SimpleNamespace(updated_at=datetime.now(UTC), run_id="live")

    existing, created = RecruitmentSyncService(Session()).request_sync(
        trigger_type=SyncTriggerType.SCHEDULED, requested_by_application="t"
    )
    assert not created and existing.run_id == "live"
    assert "pg_advisory_xact_lock" in statements[0] and statements[-1] == "COMMIT"
