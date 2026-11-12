"""One-minute mirror cadence safeguards: abandoned runs never block later
syncs, repeated ticks never duplicate rows, reconciliation is throttled when
nothing changed, and the "Delayed" threshold suits a one-minute schedule."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import app.services.mirror_sync_service as sync_mod
from app.attendance_source.mock_client import MockOnsiteSource
from app.core.constants import SyncTriggerType
from app.models.mirror import AgentStatus, AttendanceEvent, OnsiteSyncRun
from app.services import freshness_service as fs
from app.services.mirror_sync_service import MirrorSyncService
from tests.conftest import enable_site, headers_for, run_sync


def _runs(db):
    db.expire_all()
    return db.query(OnsiteSyncRun).order_by(OnsiteSyncRun.id).all()


def test_abandoned_run_is_failed_and_does_not_block_the_next_sync(api_client, db):
    stuck, started = MirrorSyncService(db).request_sync(trigger_type=SyncTriggerType.SCHEDULED)
    assert started
    stuck.status = "RUNNING"
    stuck.started_at = datetime.now(UTC) - timedelta(minutes=11)
    db.commit()

    accepted = run_sync(api_client)
    assert accepted["started"] is True and accepted["run_id"] != stuck.run_id
    runs = {r.run_id: r for r in _runs(db)}
    assert runs[stuck.run_id].status == "FAILED"
    assert "Abandoned" in runs[stuck.run_id].error_summary
    assert runs[accepted["run_id"]].status == "SUCCEEDED"
    assert db.query(AttendanceEvent).count() == 13


def test_recent_active_run_is_not_abandoned(api_client, db):
    run, _ = MirrorSyncService(db).request_sync(trigger_type=SyncTriggerType.SCHEDULED)
    run.status = "RUNNING"
    run.started_at = datetime.now(UTC) - timedelta(minutes=2)
    db.commit()
    resp = api_client.post("/api/onsite/sync", headers=headers_for("ONSITE_ADMIN"))
    assert resp.json()["run_id"] == run.run_id and resp.json()["started"] is False
    assert _runs(db)[-1].status == "RUNNING"


def test_many_one_minute_ticks_never_duplicate_rows(api_client, db):
    for _ in range(5):
        run_sync(api_client)
    runs = _runs(db)
    assert [r.status for r in runs] == ["SUCCEEDED"] * 5
    assert sum(r.events_inserted for r in runs) == 13
    assert db.query(AttendanceEvent).count() == 13


def test_reconciliation_throttled_when_nothing_changed(api_client, db, monkeypatch):
    run_sync(api_client)
    run_sync(api_client)
    first, second = _runs(db)
    assert first.reconciliation_json is not None  # inserted rows => reconciled
    assert second.reconciliation_json is None  # no change, within sync_reconcile_minutes
    assert MirrorSyncService(db).last_reconciled().run_id == first.run_id

    # A new event => reconciled straight away.
    source = MockOnsiteSource()
    newest = max(source.events, key=lambda e: e.received_utc)
    source.events.append(replace(newest, event_id="dev-site:1:999", source_transaction_id=999,
                                 received_utc=newest.received_utc + timedelta(seconds=30)))
    monkeypatch.setattr(sync_mod, "get_onsite_source", lambda: source)
    run_sync(api_client)
    third = _runs(db)[-1]
    assert third.events_inserted == 1 and third.reconciliation_json is not None
    assert all(r["in_sync"] for r in json.loads(third.reconciliation_json))


def test_reconciliation_runs_again_after_interval(api_client, db):
    run_sync(api_client)
    first = _runs(db)[0]
    first.completed_at = datetime.now(UTC) - timedelta(minutes=16)
    db.commit()
    run_sync(api_client)
    assert _runs(db)[-1].reconciliation_json is not None


def test_admin_health_reports_last_reconciliation_not_blank(api_client, db):
    run_sync(api_client)
    run_sync(api_client)
    enable_site(api_client, "dev-site")
    body = api_client.get("/api/onsite/admin/health", headers=headers_for("ONSITE_ADMIN")).json()
    assert body["reconciliation"] and all(r["in_sync"] for r in body["reconciliation"])


def test_delayed_after_a_few_missed_minutes(api_client, db):
    run_sync(api_client)
    agent = db.get(AgentStatus, "dev-site")
    synced = MirrorSyncService(db).last_successful().completed_at
    synced = synced if synced.tzinfo else synced.replace(tzinfo=UTC)
    agent.last_heartbeat_utc = synced
    agent.pending_count = 0
    db.commit()
    state = lambda now: fs.freshness(db, allowed_site_ids=("dev-site",), now=now)["sites"][0]["feed_state"]  # noqa: E731
    assert state(synced + timedelta(minutes=3)) == "FRESH"
    assert state(synced + timedelta(minutes=6)) == "DELAYED"
