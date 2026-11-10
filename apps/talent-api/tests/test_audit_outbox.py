"""Reconcile audit events commit with their changes and reach Platform Core once."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import update

from app.db.session import SessionLocal, engine
from app.models.application import Application
from app.models.audit_outbox import DELIVERED, FAILED, PENDING, AuditOutbox
from app.services import audit_outbox_service as outbox
from app.services import recruitment_consumer_service as consumer
from app.services.audit_service import AuditService
from tests.conftest import FakeRecruitmentClient
from tests.test_reconcile_pagination import REAL_SHAPE, _posting, _rows


class Platform:
    """Platform Core's contract: one record per event_id, whatever the retries."""

    def __init__(self):
        self.records = {}
        self.calls = 0
        self.lock = threading.Lock()
        self.fail = None  # callable(event) returning an exception or status code

    def __call__(self, request):
        event = json.loads(request.content)
        with self.lock:
            self.calls += 1
            outcome = self.fail(event) if self.fail else None
            if isinstance(outcome, Exception):
                raise outcome
            if isinstance(outcome, int):
                return httpx.Response(outcome)
            first = event["event_id"] not in self.records
            self.records.setdefault(event["event_id"], event)
            lost = outcome == "lost_ack"
        if lost:
            raise httpx.ReadTimeout("acknowledgment lost")
        body = {"status": "ok" if first else "duplicate", "event_id": event["event_id"]}
        return httpx.Response(201 if first else 200, json=body)

    def client(self):
        return httpx.Client(base_url="http://platform", transport=httpx.MockTransport(self))


def _reconcile(db, world, count=3, **source):
    src = FakeRecruitmentClient([_posting(world["abc"].name)], candidacies=_rows(count), **source)
    return consumer.run_reconcile(db, client=src)


def _rows_in(db, status=None):
    db.expire_all()
    query = db.query(AuditOutbox)
    return (query.filter_by(status=status) if status else query).all()


def _due(db):
    db.execute(update(AuditOutbox).values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1), claimed_until=None))
    db.commit()


def test_a_successful_reconcile_persists_its_audit_events_with_the_changes(db, two_tenant_world, monkeypatch):
    sent = []
    monkeypatch.setattr("auth_client_py.PlatformClient.record_audit_event", lambda self, **k: sent.append(k))
    assert _reconcile(db, two_tenant_world)["outcome"] == "SUCCEEDED"
    rows = _rows_in(db, PENDING)
    actions = sorted(json.loads(r.payload)["action"] for r in rows)
    assert actions.count("application.system_promoted") == 3
    assert "talent_request.system_promoted" in actions and "posting.client_mapping.dtc_resolved" in actions
    assert len({r.event_id for r in rows}) == len(rows)
    assert sent == [], "audit went around the outbox"


def test_per_application_audit_detail_is_preserved(db, two_tenant_world):
    _reconcile(db, two_tenant_world, count=1)
    application = db.query(Application).one()
    body = next(json.loads(r.payload) for r in _rows_in(db) if json.loads(r.payload)["action"] == "application.system_promoted")
    assert body["entity_type"] == "Application" and body["entity_id"] == application.id
    assert body["new_state"]["candidate_id"] == application.candidate_id
    assert body["new_state"]["talent_request_id"] == application.talent_request_id
    assert body["new_state"]["lever_opportunity_id"] == application.lever_opportunity_id


def test_a_failed_read_leaves_no_audit_events(db, two_tenant_world):
    body = _reconcile(db, two_tenant_world, candidacies_down=True)
    assert body["outcome"] == "FAILED"
    assert _rows_in(db) == []


def test_an_error_after_the_writes_leaves_no_audit_events(db, two_tenant_world, monkeypatch):
    def boom(self):
        raise RuntimeError("late failure")

    monkeypatch.setattr(db, "commit", lambda: boom(None))
    src = FakeRecruitmentClient([_posting(two_tenant_world["abc"].name)], candidacies=_rows(3))
    assert consumer.run_reconcile(db, client=src)["outcome"] == "FAILED"
    monkeypatch.undo()
    assert _rows_in(db) == []


def test_other_workflows_keep_direct_delivery(db, two_tenant_world, monkeypatch):
    sent = []
    monkeypatch.setattr("auth_client_py.PlatformClient.record_audit_event", lambda self, **k: sent.append(k))
    AuditService().log(actor_id=1, action="x.y", entity_type="T", entity_id=1)
    assert len(sent) == 1 and _rows_in(db) == []


def test_delivery_marks_events_delivered_once(db, two_tenant_world):
    _reconcile(db, two_tenant_world)
    platform = Platform()
    total = len(_rows_in(db))
    result = outbox.drain(db, client=platform.client())
    assert result["delivered"] == total and result["pending"] == 0
    assert len(platform.records) == total
    assert outbox.drain(db, client=platform.client())["delivered"] == 0


def test_a_lost_acknowledgment_retries_with_the_same_event_id_and_records_once(db, two_tenant_world):
    _reconcile(db, two_tenant_world, count=1)
    platform = Platform()
    total = len(_rows_in(db))
    target = _rows_in(db)[0].event_id
    platform.fail = lambda e: "lost_ack" if e["event_id"] == target else None
    first = outbox.drain(db, client=platform.client())
    assert first["retried"] == 1 and first["pending"] == 1
    platform.fail = None
    _due(db)
    assert outbox.drain(db, client=platform.client())["pending"] == 0
    assert len(platform.records) == total
    assert db.query(AuditOutbox).filter_by(event_id=target).one().status == DELIVERED


def test_a_platform_outage_keeps_every_event_and_stops_early(db, two_tenant_world):
    _reconcile(db, two_tenant_world, count=20)
    total = len(_rows_in(db))
    platform = Platform()
    platform.fail = lambda e: httpx.ConnectError("down")
    result = outbox.drain(db, client=platform.client())
    assert result["stopped"] == "platform_unavailable" and platform.calls == outbox.STOP_AFTER_FAILURES
    assert result["pending"] == total and not platform.records
    assert all(r.claimed_until is None for r in _rows_in(db))

    platform.fail = None
    _due(db)
    assert outbox.drain(db, client=platform.client())["delivered"] == total


def test_retry_backs_off_and_records_only_a_safe_reason(db, two_tenant_world):
    _reconcile(db, two_tenant_world, count=1)
    platform = Platform()
    platform.fail = lambda e: 503
    outbox.drain(db, client=platform.client())
    failed = [r for r in _rows_in(db) if r.last_error]
    assert failed and all(r.last_error == "http_503" and r.attempts == 1 for r in failed)
    assert outbox.drain(db, client=platform.client())["delivered"] == 0, "retried before its backoff"
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert outbox._retry_at(1, now) == now + timedelta(seconds=30)
    assert outbox._retry_at(20, now) == now + timedelta(seconds=outbox.MAX_RETRY_SECONDS)


def test_a_refused_event_is_kept_and_visible_not_retried(db, two_tenant_world):
    _reconcile(db, two_tenant_world, count=1)
    target = _rows_in(db)[0].event_id
    platform = Platform()
    platform.fail = lambda e: 409 if e["event_id"] == target else None
    result = outbox.drain(db, client=platform.client())
    assert result["refused"] == 1 and result["failed"] == 1
    assert db.query(AuditOutbox).filter_by(event_id=target).one().status == FAILED


@pytest.mark.parametrize("body", [{"status": "ok"}, {}])
def test_a_platform_without_event_id_support_is_not_counted_as_delivered(db, two_tenant_world, body):
    _reconcile(db, two_tenant_world, count=1)
    calls = []
    old = httpx.Client(base_url="http://platform", transport=httpx.MockTransport(
        lambda r: calls.append(1) or httpx.Response(201, json=body)
    ))
    result = outbox.drain(db, client=old)
    assert result["delivered"] == 0 and result["pending"] == len(_rows_in(db))
    assert result["stopped"] == "platform_without_event_id" and len(calls) == 1, "each attempt is recorded there"
    assert all(r.claimed_until is None for r in _rows_in(db))


def test_a_worker_that_dies_loses_nothing(db, two_tenant_world):
    _reconcile(db, two_tenant_world, count=1)
    total = len(_rows_in(db))
    _, _, claimed = outbox.claim_batch(db)
    assert len(claimed) == total and outbox.claim_batch(db)[2] == []
    db.execute(update(AuditOutbox).values(claimed_until=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    platform = Platform()
    assert outbox.drain(db, client=platform.client())["delivered"] == total


def _expire_claims(db):
    db.execute(update(AuditOutbox).values(claimed_until=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()


def test_a_late_failure_cannot_undo_another_workers_delivery(db, two_tenant_world):
    _reconcile(db, two_tenant_world, count=1)
    stale, _, rows = outbox.claim_batch(db)
    _expire_claims(db)
    current, _, _ = outbox.claim_batch(db)
    row_id = rows[0][0]
    assert outbox._settle(db, row_id, current, status=DELIVERED, delivered_at=datetime.now(UTC))
    assert not outbox._settle(db, row_id, stale, next_attempt_at=datetime.now(UTC), last_error="ReadTimeout")
    db.expire_all()
    assert db.get(AuditOutbox, row_id).status == DELIVERED and db.get(AuditOutbox, row_id).last_error is None


def test_an_expired_worker_cannot_release_or_settle_a_newer_claim(db, two_tenant_world):
    _reconcile(db, two_tenant_world, count=1)
    stale, _, rows = outbox.claim_batch(db)
    _expire_claims(db)
    current, until, _ = outbox.claim_batch(db)
    row_id = rows[0][0]
    assert not outbox._settle(db, row_id, stale, next_attempt_at=datetime.now(UTC), last_error="ReadTimeout")
    outbox._release(db, stale, [row_id])
    db.expire_all()
    row = db.get(AuditOutbox, row_id)
    assert row.claim_token == current and row.claimed_until is not None and row.last_error is None
    assert outbox.claim_batch(db)[2] == [], "a third worker took a row that is still claimed"


def test_no_send_starts_on_a_claim_about_to_expire(db, two_tenant_world, monkeypatch):
    _reconcile(db, two_tenant_world, count=3)
    platform = Platform()
    clock = [datetime.now(UTC)]
    monkeypatch.setattr(outbox, "_utcnow", lambda: clock[0])

    def slow(event):
        clock[0] += timedelta(seconds=outbox.CLAIM_SECONDS)  # this send outlived the claim

    platform.fail = slow
    result = outbox.drain(db, client=platform.client(), run_seconds=10_000)
    assert result["stopped"] == "claim_expiring" and platform.calls == 1
    assert all(r.claim_token is None for r in _rows_in(db, PENDING))


def test_a_claim_outlasts_any_run():
    worst_send = outbox._REQUEST_TIMEOUT * 4  # connect, write, read and pool limits
    assert outbox.CLAIM_SECONDS >= outbox.RUN_SECONDS + worst_send
    assert outbox.CLAIM_MARGIN.total_seconds() >= worst_send - outbox._REQUEST_TIMEOUT


def test_only_delivered_rows_past_retention_are_purged(db, two_tenant_world):
    _reconcile(db, two_tenant_world, count=2)
    rows = _rows_in(db)
    old = datetime.now(UTC) - outbox.DELIVERED_RETENTION - timedelta(days=1)
    rows[0].status, rows[0].delivered_at = DELIVERED, old
    rows[1].status, rows[1].delivered_at = DELIVERED, datetime.now(UTC)
    rows[2].status, rows[2].next_attempt_at = FAILED, old
    db.commit()
    before = len(rows)
    assert outbox.purge_delivered(db) == 1
    assert len(_rows_in(db)) == before - 1


def test_the_drain_module_cannot_reach_reconcile_or_sync():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for path in (root / "app/services/audit_outbox_service.py", root / "scripts/drain_audit_outbox.py"):
        names = [n.module or "" for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(n, ast.ImportFrom)]
        assert not [n for n in names if "recruitment" in n or "reconcil" in n], path


def test_stats_report_the_backlog(db, two_tenant_world):
    _reconcile(db, two_tenant_world, count=1)
    total = len(_rows_in(db))
    stats = outbox.outbox_stats(db)
    assert stats["pending"] == total and stats["oldest_pending_seconds"] is not None


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="needs PostgreSQL (postgres CI job)")
def test_concurrent_workers_claim_disjoint_batches_and_deliver_once(db, two_tenant_world):
    _reconcile(db, two_tenant_world, count=600)
    total = len(_rows_in(db))
    platform = Platform()
    barrier = threading.Barrier(4)

    def work(_):
        barrier.wait(timeout=10)
        with SessionLocal() as session:
            return outbox.drain(session, client=platform.client())["delivered"]

    with ThreadPoolExecutor(4) as pool:
        delivered = list(pool.map(work, range(4)))
    assert sum(delivered) == total
    assert platform.calls == total, "an event was sent by two workers"
    assert len(platform.records) == total
    assert outbox.outbox_stats(db)["pending"] == 0


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="needs PostgreSQL (postgres CI job)")
def test_first_load_volume_persists_every_audit_event(db, two_tenant_world):
    name = two_tenant_world["abc"].name
    postings = [_posting(name, f"p{i:02}") for i in range(len(REAL_SHAPE))]
    rows = [r for i, n in enumerate(REAL_SHAPE) for r in _rows(n, posting=f"p{i:02}", prefix=f"{i:02}-")]
    src = FakeRecruitmentClient(postings, candidacies=rows)
    assert consumer.run_reconcile(db, client=src)["outcome"] == "SUCCEEDED"
    db.expire_all()
    promoted = db.query(AuditOutbox).filter(AuditOutbox.payload.like('%"application.system_promoted"%')).count()
    assert promoted == len(rows)
    assert consumer.run_reconcile(db, client=src)["outcome"] == "SUCCEEDED"
    assert db.query(AuditOutbox).filter(AuditOutbox.payload.like('%"application.system_promoted"%')).count() == promoted
