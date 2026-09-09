"""Phase 1 §1.2 — attention / SLA + detection-health engine."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from tests.conftest import headers_for


def _admin():
    return headers_for(950, role="BIRTHDAY_ADMIN")


def _order(db, **overrides):
    from app.models.birthday_order import BirthdayOrder

    defaults = dict(
        order_reference=f"BDAY-EMP{datetime.now(UTC).timestamp()}",
        employee_id=f"att-{datetime.now(UTC).timestamp()}", employee_number="1",
        employee_name="Att Person", employee_email="att@example.com",
        birthday_date=date.today() + timedelta(days=5),
        birthday_year=(date.today() + timedelta(days=5)).year,
        office_location="Colombo", quantity=1, status="PENDING_VERIFICATION",
        address_verification_status="NOT_CHECKED",
    )
    defaults.update(overrides)
    o = BirthdayOrder(**defaults)
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def test_scan_health_flags_stale_and_deferrals(db):
    from app.models.scan_run import ScanRun
    from app.services.attention_service import scan_health

    now = datetime.now(UTC)
    # last COMPLETED 3 days ago, then 2 deferrals
    db.add(ScanRun(run_id="r0", trigger="SCHEDULED", status="COMPLETED",
                   started_at=now - timedelta(days=3)))
    db.add(ScanRun(run_id="r1", trigger="SCHEDULED", status="DEFERRED_SOURCE_UNAVAILABLE",
                   started_at=now - timedelta(days=2)))
    db.add(ScanRun(run_id="r2", trigger="SCHEDULED", status="DEFERRED_SOURCE_UNAVAILABLE",
                   started_at=now - timedelta(hours=2)))
    db.commit()

    h = scan_health(db, now=now)
    assert h["consecutive_deferrals"] == 2
    assert h["stale"] is False  # last run was 2h ago
    assert h["healthy"] is False  # deferrals


def test_scan_health_stale_when_no_recent_run(db):
    from app.models.scan_run import ScanRun
    from app.services.attention_service import scan_health

    now = datetime.now(UTC)
    db.add(ScanRun(run_id="old", trigger="SCHEDULED", status="COMPLETED",
                   started_at=now - timedelta(days=2)))
    db.commit()
    h = scan_health(db, now=now)
    assert h["stale"] is True and h["healthy"] is False


def test_attention_sweep_emits_digests(db, platform_calls):
    from app.services.attention_service import run_attention_sweep

    now = datetime.now(UTC)
    # verification overdue
    _order(db, status="PENDING_VERIFICATION", verify_by=date.today() - timedelta(days=2))
    # on hold
    _order(db, status="ON_HOLD")
    # overdue delivery
    _order(db, status="CONFIRMED", delivery_date=date.today() - timedelta(days=1))

    res = run_attention_sweep(db, now=now)
    assert res["counts"]["verification_overdue"] == 1
    assert res["counts"]["on_hold"] == 1
    assert res["counts"]["overdue_delivery"] == 1
    kinds = {b["type"] for b in platform_calls["broadcasts"]}
    assert "birthday.attention.verification_overdue" in kinds
    assert "birthday.attention.on_hold" in kinds
    assert "birthday.attention.overdue_delivery" in kinds
    # one digest per rule, not one per order
    vo = [b for b in platform_calls["broadcasts"] if b["type"] == "birthday.attention.verification_overdue"]
    assert len(vo) == 1


def test_attention_sweep_silent_when_nothing_wrong(db, platform_calls):
    from app.models.scan_run import ScanRun
    from app.services.attention_service import run_attention_sweep

    db.add(ScanRun(run_id="fresh", trigger="SCHEDULED", status="COMPLETED",
                   started_at=datetime.now(UTC)))
    db.commit()
    res = run_attention_sweep(db)
    assert res["notifications_emitted"] == []
    assert platform_calls["broadcasts"] == []


def test_dashboard_exposes_new_cards(api_client, db):
    _order(db, status="ON_HOLD")
    _order(db, status="CONFIRMED", delivery_date=date.today() - timedelta(days=3))
    body = api_client.get("/api/birthday/dashboard", headers=_admin()).json()
    assert body["on_hold_count"] == 1
    assert body["overdue_delivery_count"] == 1
    assert "detection_health" in body
    assert "open_issues_count" in body and "unmatched_emails_count" in body


def test_admin_run_attention_endpoint(api_client, db):
    _order(db, status="ON_HOLD")
    r = api_client.post("/api/birthday/admin/run-attention", headers=_admin())
    assert r.status_code == 200
    assert r.json()["counts"]["on_hold"] == 1
