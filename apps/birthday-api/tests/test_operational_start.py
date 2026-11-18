"""DIJI Birthday V1 clean start: operational start boundary, single-use
pre-launch exclusion, scan gate, supplier visibility, settings validation."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.core.constants import ExceptionReason, OrderStatus
from app.integrations.people_source.mock_adapter import MockEmployeeSource
from app.models.birthday_order import BirthdayOrder
from app.models.detection_config import BirthdayDetectionConfig
from app.models.order_event import OrderEvent
from app.models.supplier import Supplier
from app.models.supplier_communication import SupplierCommunication
from app.services import operational_start_service as ops
from app.services.detection_service import compute_next_birthday_occurrence, run_daily_scan
from tests.conftest import headers_for, supplier_headers_for

ADMIN = 900


def _cfg(start: date | None, lead: int = 7) -> BirthdayDetectionConfig:
    return BirthdayDetectionConfig(
        normal_threshold_days=10, short_notice_threshold_days=5, urgent_threshold_days=2,
        window_lookback_days=1, window_lookahead_days=14, default_quantity=1,
        verify_buffer_days=2, acknowledgement_sla_hours=24, auto_release_enabled=True,
        operational_start_date=start, supplier_lead_time_days=lead,
    )


_seq = iter(range(1, 10_000))


def _order(db, *, birthday: date, status: str, supplier_id=None, released=False) -> BirthdayOrder:
    n = next(_seq)
    order = BirthdayOrder(
        order_reference=f"BDAY-OPS{n}-{birthday.year}-{n:05d}", employee_id=f"ops-{n}",
        employee_number=str(n), employee_name=f"Person {n}", employee_email=f"p{n}@example.com",
        birthday_date=birthday, birthday_year=birthday.year, office_location="Colombo", quantity=1,
        status=status, supplier_id=supplier_id, delivery_date=birthday,
        address_verification_status="VERIFIED",
        released_at=datetime.now(UTC) if released else None,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


# -- boundary maths -----------------------------------------------------

def test_first_eligible_is_start_plus_lead_time():
    assert ops.first_eligible_birthday(_cfg(date(2026, 11, 25), 7)) == date(2026, 12, 2)
    assert ops.first_eligible_birthday(_cfg(None)) is None


def test_pre_launch_is_per_occurrence_not_per_employee():
    cfg = _cfg(date(2026, 11, 25), 7)
    occ_2026, _ = compute_next_birthday_occurrence(11, 28, date(2026, 11, 20))
    assert occ_2026 == date(2026, 11, 28) and ops.is_pre_launch(occ_2026, cfg)
    occ_2027, year = compute_next_birthday_occurrence(11, 28, date(2026, 12, 1))
    assert (occ_2027, year) == (date(2027, 11, 28), 2027)
    assert not ops.is_pre_launch(occ_2027, cfg)
    assert not ops.is_pre_launch(date(2026, 12, 2), cfg)  # boundary is inclusive-eligible
    assert not ops.is_pre_launch(date(2026, 1, 1), _cfg(None))


# -- scan gate ------------------------------------------------------------

def test_scan_creates_nothing_before_boundary_and_resumes_after(db):
    db.add(Supplier(name="Only Bakes", lead_time_days=0, status="ACTIVE"))
    db.commit()
    client = MockEmployeeSource()
    today = date.today()

    blocked = run_daily_scan(db, client, _cfg(today + timedelta(days=200), 7), today=today)
    assert blocked["orders_created"] == 0
    assert blocked["pre_launch_skipped"] > 0
    assert db.query(BirthdayOrder).count() == 0

    open_ = run_daily_scan(db, client, _cfg(today - timedelta(days=30), 7), today=today)
    assert open_["pre_launch_skipped"] == 0
    assert open_["orders_created"] > 0


# -- one-time clean start --------------------------------------------------

def _seed_backlog(db):
    sup = Supplier(name="Backlog Bakes", status="ACTIVE")
    db.add(sup)
    db.commit()
    boundary = date.today() + timedelta(days=7)
    before = boundary - timedelta(days=3)
    orders = {
        "pending": _order(db, birthday=before, status=OrderStatus.PENDING_VERIFICATION.value),
        "attention": _order(db, birthday=before, status=OrderStatus.REQUIRES_ATTENTION.value),
        "hold": _order(db, birthday=before, status=OrderStatus.ON_HOLD.value),
        "sent": _order(db, birthday=before, status=OrderStatus.SENT_TO_SUPPLIER.value,
                       supplier_id=sup.id, released=True),
        "completed": _order(db, birthday=before, status=OrderStatus.COMPLETED.value),
        "eligible": _order(db, birthday=boundary, status=OrderStatus.PENDING_VERIFICATION.value),
    }
    return sup, orders, date.today()


def _set_settings(api_client, start: date, lead: int = 7):
    resp = api_client.patch(
        "/api/birthday/config",
        json={"operational_start_date": start.isoformat(), "supplier_lead_time_days": lead},
        headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_saving_settings_never_cancels_orders(api_client, db):
    _, orders, start = _seed_backlog(db)
    body = _set_settings(api_client, start)
    assert body["first_eligible_birthday"] == (start + timedelta(days=7)).isoformat()
    db.expire_all()
    assert db.get(BirthdayOrder, orders["pending"].id).status == OrderStatus.PENDING_VERIFICATION.value


def test_preview_shows_impact_before_apply(api_client, db):
    _, _orders, start = _seed_backlog(db)
    _set_settings(api_client, start)
    prev = api_client.get("/api/birthday/config/clean-start/preview",
                          headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN")).json()
    assert prev["total"] == 4
    assert prev["by_status"] == {"PENDING_VERIFICATION": 1, "REQUIRES_ATTENTION": 1,
                                 "ON_HOLD": 1, "SENT_TO_SUPPLIER": 1}
    assert prev["released_to_supplier"] == 1
    assert prev["already_applied"] is False


def test_apply_excludes_once_without_email_and_keeps_history(api_client, db):
    sup, orders, start = _seed_backlog(db)
    cfg = _set_settings(api_client, start)
    comms_before = db.query(SupplierCommunication).count()
    admin = headers_for(ADMIN, role="BIRTHDAY_ADMIN")

    bad = api_client.post("/api/birthday/config/clean-start",
                          json={"confirm": True, "first_eligible_birthday": "2000-01-01"}, headers=admin)
    assert bad.status_code == 409  # boundary must match the preview

    resp = api_client.post("/api/birthday/config/clean-start",
                           json={"confirm": True, "first_eligible_birthday": cfg["first_eligible_birthday"]},
                           headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["already_applied"] is True
    assert resp.json()["clean_start_excluded_count"] == 4

    db.expire_all()
    for key in ("pending", "attention", "hold", "sent"):
        o = db.get(BirthdayOrder, orders[key].id)
        assert o.status == OrderStatus.CANCELLED.value
        assert o.exception_reason == ExceptionReason.PRE_LAUNCH_EXCLUDED.value
        assert db.query(OrderEvent).filter_by(order_id=o.id, to_status="CANCELLED").count() == 1
    assert db.get(BirthdayOrder, orders["completed"].id).status == OrderStatus.COMPLETED.value
    assert db.get(BirthdayOrder, orders["eligible"].id).status == OrderStatus.PENDING_VERIFICATION.value
    assert db.query(BirthdayOrder).count() == 6  # nothing deleted
    assert db.query(SupplierCommunication).count() == comms_before  # no supplier email

    again = api_client.post("/api/birthday/config/clean-start",
                            json={"confirm": True, "first_eligible_birthday": cfg["first_eligible_birthday"]},
                            headers=admin)
    assert again.status_code == 409  # single-use

    # A later settings change never repeats the cleanup.
    _set_settings(api_client, start + timedelta(days=30))
    db.expire_all()
    assert db.get(BirthdayOrder, orders["eligible"].id).status == OrderStatus.PENDING_VERIFICATION.value


def test_apply_requires_confirmation_and_permission(api_client, db):
    _seed_backlog(db)
    _set_settings(api_client, date.today())
    body = {"confirm": False, "first_eligible_birthday": (date.today() + timedelta(days=7)).isoformat()}
    assert api_client.post("/api/birthday/config/clean-start", json=body,
                           headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN")).status_code == 422
    body["confirm"] = True
    assert api_client.post("/api/birthday/config/clean-start", json=body,
                           headers=headers_for(901, role="BIRTHDAY_USER")).status_code == 403


def test_reopened_excluded_order_is_not_re_cancelled_by_scan(api_client, db):
    _, orders, start = _seed_backlog(db)
    cfg = _set_settings(api_client, start)
    api_client.post("/api/birthday/config/clean-start",
                    json={"confirm": True, "first_eligible_birthday": cfg["first_eligible_birthday"]},
                    headers=headers_for(ADMIN, role="BIRTHDAY_ADMIN"))
    db.expire_all()
    order = db.get(BirthdayOrder, orders["pending"].id)
    order.status = OrderStatus.PENDING_VERIFICATION.value  # stands in for a deliberate reopen
    db.commit()
    run_daily_scan(db, MockEmployeeSource(), db.query(BirthdayDetectionConfig).first(), today=date.today())
    db.expire_all()
    assert db.get(BirthdayOrder, order.id).status == OrderStatus.PENDING_VERIFICATION.value


# -- supplier visibility ------------------------------------------------

def test_supplier_never_sees_unreleased_cancelled_but_sees_released_tombstone(api_client, db):
    sup = Supplier(name="Visible Bakes", status="ACTIVE")
    db.add(sup)
    db.commit()
    d = date.today() + timedelta(days=3)
    unreleased = _order(db, birthday=d, status=OrderStatus.CANCELLED.value, supplier_id=sup.id)
    released = _order(db, birthday=d, status=OrderStatus.CANCELLED.value, supplier_id=sup.id, released=True)
    headers = supplier_headers_for(db, sup)

    ids = {o["id"] for o in api_client.get("/api/birthday/portal/orders", headers=headers).json()["items"]}
    assert released.id in ids and unreleased.id not in ids
    assert api_client.get(f"/api/birthday/portal/orders/{unreleased.id}", headers=headers).status_code == 404
    assert api_client.get(f"/api/birthday/portal/orders/{released.id}", headers=headers).status_code == 200


# -- settings validation --------------------------------------------------

def test_settings_validation_is_relative_to_today(api_client, db):
    admin = headers_for(ADMIN, role="BIRTHDAY_ADMIN")
    for payload in (
        {"supplier_lead_time_days": -1},
        {"supplier_lead_time_days": 61},
        {"operational_start_date": (date.today() + timedelta(days=400)).isoformat()},
        {"operational_start_date": (date.today() - timedelta(days=400)).isoformat()},
        {"operational_start_date": "2026-02-30"},
    ):
        assert api_client.patch("/api/birthday/config", json=payload, headers=admin).status_code == 422, payload
    ok = api_client.patch("/api/birthday/config", json={"operational_start_date": None}, headers=admin)
    assert ok.status_code == 200 and ok.json()["first_eligible_birthday"] is None
