"""A retried audit delivery records one event, however the retries interleave."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.models.audit_log import AuditLog
from tests.conftest import internal_headers

URL = "/api/platform/internal/audit-events"
EVENT = {"event_id": "evt-1", "action": "application.system_promoted", "entity_type": "Application", "entity_id": 7,
         "new_state": {"talent_request_id": 3}}


def _post(api_client, body):
    return api_client.post(URL, json=body, headers=internal_headers())


def _rows():
    with SessionLocal() as s:
        return s.execute(select(AuditLog).where(AuditLog.action == EVENT["action"])).scalars().all()


def test_a_new_event_is_recorded(api_client, db):
    resp = _post(api_client, EVENT)
    assert resp.status_code == 201 and resp.json() == {"status": "ok", "event_id": "evt-1"}
    assert [r.event_id for r in _rows()] == ["evt-1"]


def test_a_lost_acknowledgment_retried_is_acknowledged_without_a_second_record(api_client, db):
    _post(api_client, EVENT)
    for _ in range(3):
        resp = _post(api_client, EVENT)
        assert resp.status_code == 200 and resp.json() == {"status": "duplicate", "event_id": "evt-1"}
    assert len(_rows()) == 1


@pytest.mark.parametrize("change", [{"entity_id": 8}, {"action": "application.other"}, {"new_state": {"talent_request_id": 4}}])
def test_reusing_an_event_id_for_different_content_is_rejected(api_client, db, change):
    _post(api_client, EVENT)
    resp = _post(api_client, {**EVENT, **change})
    assert resp.status_code == 409
    assert "talent_request_id" not in resp.text
    with SessionLocal() as s:
        assert len(s.execute(select(AuditLog).where(AuditLog.event_id == "evt-1")).scalars().all()) == 1


def test_callers_without_an_event_id_are_unchanged(api_client, db):
    body = {k: v for k, v in EVENT.items() if k != "event_id"}
    for _ in range(2):
        resp = _post(api_client, body)
        assert resp.status_code == 201 and resp.json() == {"status": "ok"}
    assert [r.event_id for r in _rows()] == [None, None]


def test_an_unknown_actor_is_not_mistaken_for_a_duplicate(api_client, db):
    if engine.dialect.name != "postgresql":
        pytest.skip("SQLite does not enforce the foreign key here")
    with pytest.raises(Exception):  # noqa: B017, PT011 - the constraint error propagates, as without event_id
        _post(api_client, {**EVENT, "actor_id": 999999})
    assert _rows() == []


@pytest.mark.parametrize("bad", ["", "x" * 65])
def test_event_id_is_bounded(api_client, db, bad):
    assert _post(api_client, {**EVENT, "event_id": bad}).status_code == 422


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="needs PostgreSQL (postgres CI job)")
def test_simultaneous_deliveries_record_one_event(api_client, db):
    barrier = threading.Barrier(8)

    def send(_):
        barrier.wait(timeout=10)
        return _post(api_client, EVENT).status_code

    with ThreadPoolExecutor(8) as pool:
        codes = sorted(pool.map(send, range(8)))
    assert codes == [200] * 7 + [201]
    assert len(_rows()) == 1
