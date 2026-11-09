"""Sync run guarantees that only real PostgreSQL transactions can prove."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, text, update

from app.db.session import SessionLocal, engine
from app.models.sync_run import RecruitmentSyncRun, SyncStatus, SyncTriggerType
from app.services import recruitment_sync_service as module
from app.services.recruitment_sync_service import RecruitmentSyncService

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="needs PostgreSQL (postgres CI job)")


@pytest.fixture(autouse=True)
def clean_runs(db):
    def wipe():
        with SessionLocal() as s:
            s.execute(delete(RecruitmentSyncRun))
            s.commit()

    wipe()
    yield
    wipe()


def _request() -> tuple[str, bool]:
    with SessionLocal() as s:
        run, created = RecruitmentSyncService(s).request_sync(
            trigger_type=SyncTriggerType.SCHEDULED, requested_by_application="test"
        )
        return run.run_id, created


def _concurrent_requests(count: int) -> list[tuple[str, bool]]:
    barrier = threading.Barrier(count)

    def go(_):
        barrier.wait()
        return _request()

    with ThreadPoolExecutor(count) as pool:
        return list(pool.map(go, range(count)))


def _insert(status: SyncStatus, age: timedelta) -> str:
    when = datetime.now(UTC) - age
    with SessionLocal() as s:
        run = RecruitmentSyncRun(
            run_id=f"run-{time.time_ns()}", provider="LEVER", trigger_type=SyncTriggerType.SCHEDULED.value,
            requested_by_application="test", correlation_id="c", status=status.value,
            started_at=when, updated_at=when,
        )
        s.add(run)
        s.commit()
        return run.run_id


def _status(run_id: str) -> str:
    with SessionLocal() as s:
        return s.execute(select(RecruitmentSyncRun.status).where(RecruitmentSyncRun.run_id == run_id)).scalar_one()


def _beat(run_id: str) -> datetime:
    with SessionLocal() as s:
        return s.execute(select(RecruitmentSyncRun.updated_at).where(RecruitmentSyncRun.run_id == run_id)).scalar_one()


def _queue_with(monkeypatch, sync_postings) -> str:
    run_id, created = _request()
    assert created
    monkeypatch.setattr(module.LeverPostingSyncService, "sync_postings", sync_postings)
    monkeypatch.setattr(module.LeverCandidacySyncService, "sync_opportunities", lambda self, limit: {})
    monkeypatch.setattr(module.platform_notify, "notify_module_role", lambda **kw: None)
    return run_id


def test_two_replicas_cannot_start_concurrent_syncs():
    results = _concurrent_requests(8)
    assert sum(created for _, created in results) == 1
    assert len({run_id for run_id, _ in results}) == 1


def test_crashed_run_is_recovered_once_by_racing_replicas():
    crashed = _insert(SyncStatus.RUNNING, timedelta(hours=1))
    results = _concurrent_requests(8)
    assert sum(created for _, created in results) == 1
    assert _status(crashed) == SyncStatus.FAILED.value


def test_heartbeat_commits_while_the_run_transaction_stays_open(monkeypatch):
    monkeypatch.setattr(module, "_HEARTBEAT_SECONDS", 0.2)
    monkeypatch.setattr(module, "_ABANDONED_AFTER", timedelta(seconds=1))
    seen = {}

    def slow(self):
        # Uncommitted work on the run's own connection, as during a real sync.
        self.db.execute(text("SELECT txid_current()"))
        start = _beat(run_id)
        time.sleep(2.5)
        seen["advanced"] = _beat(run_id) > start
        seen["second_request"] = _request()
        return {"total": 0}

    run_id = _queue_with(monkeypatch, slow)
    RecruitmentSyncService.execute_run(run_id)
    assert seen["advanced"]
    assert seen["second_request"] == (run_id, False), "a slow live run was abandoned"
    assert _status(run_id) == SyncStatus.SUCCEEDED.value


def test_abandoned_run_cannot_overwrite_its_outcome_or_a_newer_run(monkeypatch):
    newer = {}

    def overtaken(self):
        with SessionLocal() as s:
            s.execute(
                update(RecruitmentSyncRun).where(RecruitmentSyncRun.run_id == run_id)
                .values(status=SyncStatus.FAILED.value, updated_at=datetime.now(UTC) - timedelta(hours=1))
            )
            s.commit()
        newer["id"] = _request()[0]
        return {"total": 0}

    run_id = _queue_with(monkeypatch, overtaken)
    RecruitmentSyncService.execute_run(run_id)
    assert _status(run_id) == SyncStatus.FAILED.value
    assert _status(newer["id"]) == SyncStatus.QUEUED.value


def test_finish_waits_for_an_abandon_in_progress(monkeypatch):
    """Without the row lock, the finisher reads RUNNING and then overwrites FAILED."""

    def abandoned_mid_finish(self):
        holder = SessionLocal()
        holder.execute(
            update(RecruitmentSyncRun).where(RecruitmentSyncRun.run_id == run_id)
            .values(status=SyncStatus.FAILED.value)
        )

        def commit_later():
            time.sleep(0.5)
            holder.commit()
            holder.close()

        threading.Thread(target=commit_later).start()
        return {"total": 0}

    run_id = _queue_with(monkeypatch, abandoned_mid_finish)
    RecruitmentSyncService.execute_run(run_id)
    assert _status(run_id) == SyncStatus.FAILED.value


def test_abandon_waits_for_a_finish_in_progress():
    """A stale-looking run being finished must keep its result."""
    finishing = _insert(SyncStatus.RUNNING, timedelta(hours=1))
    holder = SessionLocal()
    holder.execute(
        update(RecruitmentSyncRun).where(RecruitmentSyncRun.run_id == finishing)
        .values(status=SyncStatus.SUCCEEDED.value)
    )
    with ThreadPoolExecutor(1) as pool:
        request = pool.submit(_request)
        time.sleep(0.5)
        assert not request.done(), "request_sync did not wait for the row lock"
        holder.commit()
        holder.close()
        _, created = request.result(timeout=10)
    assert created
    assert _status(finishing) == SyncStatus.SUCCEEDED.value
