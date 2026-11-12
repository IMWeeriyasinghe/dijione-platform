"""Phase 1.6 §2/§3/§21 — the DEV data-reset script. Calls
reset_workflow_data() directly (no HTTP layer — it deliberately isn't one)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from scripts.reset_workflow_data import CONFIRM_TOKEN, ResetRefusedError, reset_workflow_data


def _seed_full_workflow_data(db):
    from app.models.birthday_order import BirthdayOrder
    from app.models.inbound_email import InboundEmail
    from app.models.order_event import OrderEvent
    from app.models.order_issue import OrderIssue
    from app.models.scan_run import ScanRun
    from app.models.special_requirement import SpecialRequirement
    from app.models.supplier import Supplier
    from app.models.supplier_catalogue_item import SupplierCatalogueItem
    from app.models.supplier_communication import SupplierCommunication
    from app.models.supplier_location import SupplierLocation
    from app.models.supplier_user import SupplierUser

    supplier = Supplier(name="Reset Bakery", primary_contact_email="reset@bakery.example.com", is_default=True)
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    db.add(SupplierLocation(supplier_id=supplier.id, office_location="Colombo"))
    db.add(SupplierCatalogueItem(supplier_id=supplier.id, name="Sponge", is_active=True, is_default=True))
    db.add(SupplierUser(supplier_id=supplier.id, email="u@bakery.example.com", full_name="U", status="ACTIVE"))

    order = BirthdayOrder(
        order_reference="BDAY-EMPreset-1-2026-00001", employee_id="reset-1",
        employee_name="Reset Person", employee_email="reset@example.com",
        birthday_date=date.today() + timedelta(days=10),
        birthday_year=(date.today() + timedelta(days=10)).year,
        office_location="Colombo", status="SENT_TO_SUPPLIER", supplier_id=supplier.id,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    db.add(OrderEvent(order_id=order.id, event_type="STATUS_CHANGE", actor_type="SYSTEM"))
    db.add(OrderIssue(order_id=order.id, raised_by_type="SUPPLIER", raised_by_id=1, type="OTHER", detail="x", status="OPEN"))
    db.add(SpecialRequirement(order_id=order.id, kind="INTERNAL_NOTE", text="note", created_by=1))
    db.add(SupplierCommunication(
        order_id=order.id, supplier_id=supplier.id, direction="OUTBOUND", channel="EMAIL",
        author_type="SYSTEM", status="SENT",
    ))
    db.add(InboundEmail(
        from_address="x@example.com", subject="s", body_preview="b",
        status="UNMATCHED", reason="no order reference", provider_message_id="m1",
    ))
    from datetime import UTC, datetime

    db.add(ScanRun(run_id="r1", trigger="SCHEDULED", status="COMPLETED", started_at=datetime.now(UTC)))
    db.commit()
    return supplier


def test_reset_clears_workflow_data_preserves_supplier_config(db):
    supplier = _seed_full_workflow_data(db)

    result = reset_workflow_data(db, confirm=CONFIRM_TOKEN, environment="development")

    assert result["before"]["birthday_orders"] == 1
    assert result["after"]["birthday_orders"] == 0
    assert result["after"]["order_events"] == 0
    assert result["after"]["order_issues"] == 0
    assert result["after"]["special_requirements"] == 0
    assert result["after"]["supplier_communications"] == 0
    assert result["after"]["inbound_emails"] == 0
    assert result["after"]["scan_runs"] == 0

    # Preserved, byte-for-byte.
    assert result["after"]["suppliers"] == result["before"]["suppliers"] == 1
    assert result["after"]["supplier_users"] == result["before"]["supplier_users"] == 1
    assert result["after"]["supplier_catalogue_items"] == result["before"]["supplier_catalogue_items"] == 1

    from app.models.supplier import Supplier
    from app.models.supplier_location import SupplierLocation

    refreshed = db.get(Supplier, supplier.id)
    assert refreshed is not None and refreshed.name == "Reset Bakery" and refreshed.is_default is True
    assert db.query(SupplierLocation).filter_by(supplier_id=supplier.id).count() == 1


def test_reset_rejects_wrong_confirm_token(db):
    _seed_full_workflow_data(db)
    with pytest.raises(ResetRefusedError):
        reset_workflow_data(db, confirm="not-the-token", environment="development")
    from app.models.birthday_order import BirthdayOrder

    assert db.query(BirthdayOrder).count() == 1  # untouched


def test_reset_rejects_mismatched_environment(db):
    _seed_full_workflow_data(db)
    with pytest.raises(ResetRefusedError):
        reset_workflow_data(db, confirm=CONFIRM_TOKEN, environment="production")
    from app.models.birthday_order import BirthdayOrder

    assert db.query(BirthdayOrder).count() == 1  # untouched


def test_reset_does_not_clear_inbound_emails_when_email_mode_is_not_mock(db, monkeypatch):
    from app.core.config import get_settings

    _seed_full_workflow_data(db)
    settings = get_settings()
    monkeypatch.setattr(settings, "email_sending_mode", "live")
    try:
        result = reset_workflow_data(db, confirm=CONFIRM_TOKEN, environment=settings.app_env)
    finally:
        monkeypatch.setattr(settings, "email_sending_mode", "mock")

    assert result["after"]["inbound_emails"] == 1  # left alone
    assert result["after"]["birthday_orders"] == 0  # everything else still clears
