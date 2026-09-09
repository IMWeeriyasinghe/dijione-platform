"""Phase 1 §1.5 — inbound supplier email (polling-only). Correlation,
sender validation, quarantine, idempotency, no-auto-issue, threading,
manual link/dismiss, watermark.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.integrations.inbound_mail.client import InboundMessage
from app.integrations.inbound_mail.mock_client import MockInboundMailClient
from tests.conftest import headers_for, supplier_headers_for


def _released_order(api_client, db, *, supplier_user_email="baker@bakery.example.com"):
    from app.models.supplier import Supplier
    from app.models.supplier_user import SupplierUser

    supplier = Supplier(
        name="Inbound Bakery", status="ACTIVE", is_default=True,
        primary_contact_email="contact@bakery.example.com", lead_time_days=3,
        working_days="Mon,Tue,Wed,Thu,Fri,Sat,Sun",
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    db.add(SupplierUser(
        supplier_id=supplier.id, email=supplier_user_email, full_name="Baker", status="ACTIVE",
    ))
    db.commit()
    admin = headers_for(900, role="BIRTHDAY_ADMIN")
    payload = {
        "employee_id": "ib-1", "employee_number": "9200", "employee_name": "Inbound Person",
        "employee_email": "ip@example.com",
        "birthday_date": str(datetime.now(UTC).date() + timedelta(days=12)),
        "office_location": "Colombo",
    }
    o = api_client.post("/api/birthday/orders", json=payload, headers=admin).json()
    oid = o["id"]
    api_client.patch(
        f"/api/birthday/orders/{oid}",
        json={"supplier_id": supplier.id, "delivery_date": str(datetime.now(UTC).date() + timedelta(days=11))},
        headers=admin,
    )
    v = api_client.post(f"/api/birthday/orders/{oid}/verify", json={}, headers=admin)
    assert v.json()["order"]["status"] == "SENT_TO_SUPPLIER"
    return oid, o["order_reference"], supplier, admin


def _ingest(db, **kw):
    from app.services.inbound_email_service import ingest_message

    kw.setdefault("id", f"m-{datetime.now(UTC).timestamp()}")
    kw.setdefault("received_at", datetime.now(UTC))
    return ingest_message(db, InboundMessage(**kw))


def test_correlates_by_order_reference_and_creates_no_issue(api_client, db):
    oid, ref, supplier, admin = _released_order(api_client, db)
    out = _ingest(
        db, from_address="baker@bakery.example.com",
        subject=f"Re: [{ref}] Birthday Cake Order",
        body_text="Confirmed, we'll deliver at 10am.",
    )
    assert out == "matched"
    tl = api_client.get(f"/api/birthday/orders/{oid}/timeline", headers=admin).json()
    inbound = [e for e in tl["entries"] if e["kind"] == "email" and e["direction"] == "INBOUND"]
    assert len(inbound) == 1 and "deliver at 10am" in inbound[0]["body"]
    assert api_client.get(f"/api/birthday/orders/{oid}/issues", headers=admin).json() == []


def test_correlates_by_in_reply_to_header(api_client, db):
    from app.models.supplier_communication import SupplierCommunication

    oid, ref, supplier, admin = _released_order(api_client, db)
    outbound = db.query(SupplierCommunication).filter_by(
        order_id=oid, direction="OUTBOUND", status="SENT",
    ).first()
    assert outbound is not None and outbound.message_id
    out = _ingest(
        db, from_address="baker@bakery.example.com", subject="Re: your order",
        body_text="No reference in the body at all.", in_reply_to=[outbound.message_id],
    )
    assert out == "matched"


def test_wrong_sender_is_quarantined(api_client, db):
    oid, ref, supplier, admin = _released_order(api_client, db)
    out = _ingest(
        db, from_address="random@stranger.example.com",
        subject=f"Re: [{ref}]", body_text="hello",
    )
    assert out == "quarantined"
    q = api_client.get("/api/birthday/inbound-emails", headers=admin).json()
    assert len(q) == 1 and q[0]["reason"].startswith("sender")


def test_cross_supplier_reply_is_quarantined(api_client, db):
    from app.models.supplier import Supplier
    from app.models.supplier_user import SupplierUser

    oid, ref, supplier, admin = _released_order(api_client, db)
    other = Supplier(name="Other", primary_contact_email="o@o.example.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    db.add(SupplierUser(supplier_id=other.id, email="spy@other.example.com", status="ACTIVE"))
    db.commit()

    out = _ingest(
        db, from_address="spy@other.example.com", subject=f"Re: [{ref}]", body_text="peeking",
    )
    assert out == "quarantined"


def test_no_order_reference_is_quarantined(api_client, db):
    oid, ref, supplier, admin = _released_order(api_client, db)
    out = _ingest(db, from_address="baker@bakery.example.com", subject="hi", body_text="no ref")
    assert out == "quarantined"


def test_duplicate_message_id_is_skipped(api_client, db):
    oid, ref, supplier, admin = _released_order(api_client, db)
    mid = "dup-1"
    a = _ingest(db, id=mid, from_address="baker@bakery.example.com",
                subject=f"[{ref}]", body_text="first")
    b = _ingest(db, id=mid, from_address="baker@bakery.example.com",
                subject=f"[{ref}]", body_text="second")
    assert a == "matched" and b == "duplicate"


def test_html_body_is_stripped(api_client, db):
    oid, ref, supplier, admin = _released_order(api_client, db)
    _ingest(
        db, from_address="baker@bakery.example.com", subject=f"[{ref}]",
        body_text="<p>Hi <b>there</b> <script>evil()</script></p>",
    )
    from app.models.supplier_communication import SupplierCommunication

    c = db.query(SupplierCommunication).filter_by(order_id=oid, direction="INBOUND").one()
    assert "<" not in c.body and "evil" not in c.body and "Hi there" in c.body


def test_threaded_reply_inherits_existing_issue_id(api_client, db):
    from app.models.supplier_communication import SupplierCommunication

    oid, ref, supplier, admin = _released_order(api_client, db)
    sup = supplier_headers_for(db, supplier)
    # supplier raises a structured issue; internal messages on it via email copy
    issue = api_client.post(
        f"/api/birthday/portal/orders/{oid}/issues",
        json={"type": "DELIVERY_ISSUE", "detail": "van broke down"}, headers=sup,
    ).json()
    api_client.post(
        f"/api/birthday/orders/{oid}/messages",
        json={"body": "Understood — can you deliver tomorrow?", "issue_id": issue["id"], "also_email": True},
        headers=admin,
    )
    outbound = db.query(SupplierCommunication).filter_by(
        order_id=oid, channel="EMAIL", direction="OUTBOUND",
    ).order_by(SupplierCommunication.id.desc()).first()
    outbound.issue_id = issue["id"]
    db.commit()

    _ingest(
        db, from_address="baker@bakery.example.com", subject="Re: update",
        body_text="Yes tomorrow works.", in_reply_to=[outbound.message_id],
    )
    inbound = db.query(SupplierCommunication).filter_by(
        order_id=oid, channel="EMAIL", direction="INBOUND",
    ).one()
    assert inbound.issue_id == issue["id"]


def test_manual_link_and_dismiss(api_client, db):
    oid, ref, supplier, admin = _released_order(api_client, db)
    # two quarantined mails
    _ingest(db, from_address="random1@x.example.com", subject="no ref 1", body_text="a")
    _ingest(db, from_address="random2@x.example.com", subject="no ref 2", body_text="b")
    q = api_client.get("/api/birthday/inbound-emails", headers=admin).json()
    assert len(q) == 2

    linked = api_client.post(
        f"/api/birthday/inbound-emails/{q[0]['id']}/link",
        json={"order_id": oid, "raise_issue": True, "issue_type": "OTHER"}, headers=admin,
    )
    assert linked.status_code == 200 and linked.json()["status"] == "LINKED"
    assert len(api_client.get(f"/api/birthday/orders/{oid}/issues", headers=admin).json()) == 1
    from app.models.supplier_communication import SupplierCommunication

    assert db.query(SupplierCommunication).filter_by(order_id=oid, direction="INBOUND").count() == 1

    dismissed = api_client.post(
        f"/api/birthday/inbound-emails/{q[1]['id']}/dismiss", headers=admin,
    )
    assert dismissed.json()["status"] == "DISMISSED"
    assert api_client.get("/api/birthday/inbound-emails", headers=admin).json() == []


def test_poll_advances_watermark(api_client, db):
    from app.services.inbound_email_service import poll

    MockInboundMailClient.reset()
    oid, ref, supplier, admin = _released_order(api_client, db)
    t0 = datetime.now(UTC)
    MockInboundMailClient.enqueue(InboundMessage(
        id="p-1", from_address="baker@bakery.example.com", subject=f"[{ref}]",
        body_text="one", received_at=t0,
    ))
    r1 = poll(db)
    assert r1["matched"] == 1 and r1["watermark_advanced"] is True
    # a second poll with nothing newer -> no-op
    r2 = poll(db)
    assert r2["seen"] == 0
    MockInboundMailClient.reset()
