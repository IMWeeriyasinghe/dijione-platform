"""Incremental raw mirror: idempotency, overlap, single-flight, failure
preserves the mirror, raw values verbatim, reconciliation drift."""

import json
from dataclasses import replace
from datetime import timedelta

import app.services.mirror_sync_service as sync_mod
from app.attendance_source.client import SourceUnavailableError
from app.attendance_source.mock_client import MockOnsiteSource
from app.core.constants import SyncTriggerType
from app.models.mirror import AttendanceEvent, OnsiteSyncRun, SiteSettings, SyncState
from app.services.mirror_sync_service import MirrorSyncService
from tests.conftest import headers_for, internal_headers, run_sync


def _use_source(monkeypatch, source):
    monkeypatch.setattr(sync_mod, "get_onsite_source", lambda: source)


def _latest_run(db):
    db.expire_all()
    return db.query(OnsiteSyncRun).order_by(OnsiteSyncRun.id.desc()).first()


def test_first_sync_mirrors_all_events_and_discovers_sites_disabled(api_client, db):
    run_sync(api_client)
    run = _latest_run(db)
    assert run.status == "SUCCEEDED"
    assert (run.events_read, run.events_inserted, run.events_existing) == (13, 13, 0)
    assert db.query(AttendanceEvent).count() == 13
    settings = {s.site_id: s.enabled for s in db.query(SiteSettings).all()}
    assert settings == {"dev-site": False, "syd-site": False}  # fail closed


def test_raw_values_preserved_verbatim(api_client, db):
    source = MockOnsiteSource()
    run_sync(api_client)
    mirrored = {e.event_id: e for e in db.query(AttendanceEvent).all()}
    for src in source.events:
        row = mirrored[src.event_id]
        for field in ("site_id", "source_epoch", "source_transaction_id", "emp_code", "punch_time_local",
                      "punch_time_utc", "time_zone", "punch_state", "verify_type", "record_hash", "received_utc",
                      "batch_id", "terminal_sn"):
            assert getattr(row, field) == getattr(src, field), field
    assert {e.punch_state for e in mirrored.values()} == {"255"}  # raw, never IN/OUT
    assert mirrored["dev-site:1000:104"].emp_code == "0107"  # leading zero kept
    epochs = {(e.site_id, e.source_epoch) for e in mirrored.values()}
    assert {("dev-site", 1), ("dev-site", 1000), ("syd-site", 1)} == epochs


def test_second_sync_is_idempotent(api_client, db):
    run_sync(api_client)
    run_sync(api_client)
    run = _latest_run(db)
    assert run.status == "SUCCEEDED"
    assert run.events_inserted == 0
    assert db.query(AttendanceEvent).count() == 13


def test_overlap_picks_up_late_committed_events(api_client, db, monkeypatch):
    source = MockOnsiteSource()
    _use_source(monkeypatch, source)
    run_sync(api_client)
    hwm = db.get(SyncState, 1).high_water_received_utc
    # A batch that committed late with an earlier ReceivedUtc than the
    # high-water mark (inside the 10-minute overlap) must still be mirrored.
    late = replace(source.events[0], event_id="dev-site:1:50000", source_epoch=1, source_transaction_id=50000,
                   received_utc=hwm - timedelta(minutes=5))
    too_old = replace(source.events[0], event_id="dev-site:1:50001", source_epoch=1, source_transaction_id=50001,
                      received_utc=hwm - timedelta(minutes=30))
    source.events.extend([late, too_old])
    run_sync(api_client)
    ids = {e.event_id for e in db.query(AttendanceEvent).all()}
    assert "dev-site:1:50000" in ids
    assert "dev-site:1:50001" not in ids  # outside overlap; surfaced by reconciliation drift instead
    recon = json.loads(_latest_run(db).reconciliation_json)
    dev1 = next(r for r in recon if r["site_id"] == "dev-site" and r["source_epoch"] == 1)
    assert dev1["source_count"] == 3 and dev1["mirror_count"] == 2 and dev1["in_sync"] is False


def test_paging_across_small_pages(api_client, db, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "sync_page_size", 4)
    run_sync(api_client)
    assert db.query(AttendanceEvent).count() == 13


def test_single_flight(api_client, db):
    run, started = MirrorSyncService(db).request_sync(trigger_type=SyncTriggerType.AD_HOC)
    assert started
    resp = api_client.post("/api/onsite/sync", headers=headers_for("ONSITE_ADMIN"))
    assert resp.status_code == 202
    assert resp.json()["run_id"] == run.run_id and resp.json()["started"] is False


class _Unavailable(MockOnsiteSource):
    def list_sites(self):
        raise SourceUnavailableError("paused")


class _FailsMidway(MockOnsiteSource):
    def read_events_after(self, *a, **kw):
        raise RuntimeError("boom")


def test_failed_sync_preserves_mirror(api_client, db, monkeypatch):
    run_sync(api_client)
    for failing in (_Unavailable(), _FailsMidway()):
        _use_source(monkeypatch, failing)
        run_sync(api_client)
        run = _latest_run(db)
        assert run.status == "FAILED"
        assert db.query(AttendanceEvent).count() == 13
    assert _latest_run(db).source_unavailable is False
    _use_source(monkeypatch, _Unavailable())
    run_sync(api_client)
    assert _latest_run(db).source_unavailable is True


def test_reconciliation_in_sync_after_full_sync(api_client, db):
    run_sync(api_client)
    recon = json.loads(_latest_run(db).reconciliation_json)
    assert [(r["site_id"], r["source_epoch"], r["source_count"], r["in_sync"]) for r in recon] == [
        ("dev-site", 1, 1, True), ("dev-site", 1000, 9, True), ("syd-site", 1, 3, True),
    ]


def test_mirror_never_deletes_rows_missing_from_source(api_client, db, monkeypatch):
    source = MockOnsiteSource()
    _use_source(monkeypatch, source)
    run_sync(api_client)
    source.events = [e for e in source.events if e.site_id != "syd-site"]
    run_sync(api_client)
    assert db.query(AttendanceEvent).count() == 13
    recon = json.loads(_latest_run(db).reconciliation_json)
    syd = next(r for r in recon if r["site_id"] == "syd-site")
    assert syd["source_count"] == 0 and syd["mirror_count"] == 3 and syd["in_sync"] is False


def test_scheduled_sync_requires_internal_token(api_client, db):
    assert api_client.post("/api/onsite/internal/scheduled-sync").status_code == 401
    assert api_client.post("/api/onsite/internal/scheduled-sync", headers=internal_headers()).status_code == 202


def test_sync_history_and_run_lookup(api_client, db):
    run_id = run_sync(api_client)["run_id"]
    h = headers_for("ONSITE_ADMIN")
    assert api_client.get(f"/api/onsite/sync/runs/{run_id}", headers=h).json()["status"] == "SUCCEEDED"
    assert api_client.get("/api/onsite/sync/runs/nope", headers=h).status_code == 404
    assert len(api_client.get("/api/onsite/sync/history", headers=h).json()) == 1
