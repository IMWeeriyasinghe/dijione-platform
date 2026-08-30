"""One-off, idempotent correction: rewrite BirthdayOrder.order_reference
rows that embed BambooHR's internal record ``id`` instead of the
business-facing ``employeeNumber`` (Team Member ID).

Context
-------
``order_sequence_service.next_order_reference`` used to be called with
``employee_id`` (BambooHR internal id, e.g. 530) instead of
``employee_number`` (the operational Team Member ID, e.g. 396), producing
references like ``BDAY-EMP530-2026-00007`` where they should read
``BDAY-EMP396-2026-00007``. Detection and manual creation now pass the
correct token; this script fixes rows created before that change.

Safety / determinism
--------------------
A row is corrected ONLY when all of these hold:
  * ``employee_number`` is present on the row and differs from
    ``employee_id`` (so the wrong token is unambiguous);
  * the reference parses as ``BDAY-EMP<token>-<year>-<seq>`` and
    ``<token>`` is exactly the row's ``employee_id`` (proving it is the
    internal id, not some other value);
  * the corrected reference (``EMP<employee_number>`` with the SAME year
    and sequence number) is not already used by another order.

The ``<year>`` and 5-digit ``<seq>`` are preserved verbatim, so historical
order identity / ordering is kept — only the EMP token changes.

By default a row that has already progressed to a supplier-visible status
(SENT_TO_SUPPLIER or later) is left untouched and reported, because the
reference is the correlation key a supplier/email may already have seen.
Pass ``--force`` to rewrite those too (dev/UAT only).

Idempotent: a second run finds every row already correct and changes
nothing.

Usage (from apps/birthday-api):
    python -m scripts.backfill_order_references [--dry-run] [--force]
"""

from __future__ import annotations

import re
import sys

from app.db.session import SessionLocal
from app.models.birthday_order import BirthdayOrder

_REF_RE = re.compile(r"^BDAY-EMP(?P<token>.+)-(?P<year>\d{4})-(?P<seq>\d{5})$")

_SUPPLIER_VISIBLE = {
    "SENT_TO_SUPPLIER", "SUPPLIER_REVIEW", "CHANGE_REQUESTED", "CONFIRMED",
    "PREPARING", "OUT_FOR_DELIVERY", "DELIVERED", "COMPLETED", "UNABLE_TO_FULFIL",
}


def run(*, dry_run: bool = False, force: bool = False) -> dict:
    db = SessionLocal()
    corrected: list[tuple[str, str]] = []
    counts = {
        "scanned": 0,
        "already_correct": 0,
        "no_team_member_id": 0,
        "unparseable": 0,
        "token_not_internal_id": 0,
        "collision": 0,
        "progressed_skipped": 0,
    }
    try:
        orders = db.query(BirthdayOrder).all()
        all_refs = {o.order_reference for o in orders}

        for order in orders:
            counts["scanned"] += 1
            emp_number = (order.employee_number or "").strip()
            emp_id = (order.employee_id or "").strip()

            if not emp_number or emp_number == emp_id:
                counts["no_team_member_id"] += 1
                continue

            m = _REF_RE.match(order.order_reference or "")
            if m is None:
                counts["unparseable"] += 1
                continue

            token, year, seq = m.group("token"), m.group("year"), m.group("seq")
            if token == emp_number:
                counts["already_correct"] += 1
                continue
            if token != emp_id:
                # Some other value — cannot prove it is wrong, leave it.
                counts["token_not_internal_id"] += 1
                continue

            new_ref = f"BDAY-EMP{emp_number}-{year}-{seq}"
            if new_ref in all_refs:
                counts["collision"] += 1
                print(f"  COLLISION: {order.order_reference} -> {new_ref} already exists; skipped")
                continue
            if order.status in _SUPPLIER_VISIBLE and not force:
                counts["progressed_skipped"] += 1
                print(
                    f"  PROGRESSED ({order.status}): {order.order_reference} left as-is "
                    f"(would be {new_ref}); pass --force to rewrite"
                )
                continue

            print(f"  {order.order_reference}  ->  {new_ref}")
            corrected.append((order.order_reference, new_ref))
            if not dry_run:
                order.order_reference = new_ref
                all_refs.discard(m.string)
                all_refs.add(new_ref)

        if dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()

    summary = {"corrected": len(corrected), "dry_run": dry_run, "force": force, **counts}
    print("Order-reference backfill complete:", summary)
    return summary


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv, force="--force" in sys.argv)
