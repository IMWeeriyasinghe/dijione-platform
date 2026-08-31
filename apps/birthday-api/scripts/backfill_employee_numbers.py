"""One-off backfill: populate BirthdayOrder.employee_number for existing
rows from BambooHR's `employeeNumber` field (via people-api — Architecture
Completion Plan §3, birthday-api holds no BambooHR credential).

Context: `employee_id` on BirthdayOrder has always stored BambooHR's
internal record `id` (e.g. "366"), not the operational Employee ID
Dijital Team actually uses (e.g. "239", BambooHR's `employeeNumber`
field) — verified live 2026-08-14 against employee Madushanka
Weeriyasinghe. New detections/creates now populate `employee_number`
directly; this script backfills rows created before that change.

Uses people-api's live-lookup escape hatch (a single read-only BambooHR GET
per employee id, since a terminated employee referenced by an old order is
never in people-api's active-employee read model). Only writes to the
local birthday.db. Idempotent/safe to re-run: always sets employee_number
from the freshly fetched value, never derives it from local state.

Usage (from apps/birthday-api):
    python -m scripts.backfill_employee_numbers
"""

from __future__ import annotations

from app.db.session import SessionLocal
from app.integrations.factory import get_employee_source
from app.integrations.people_source.client import EmployeeSourceFetchError
from app.integrations.people_source.mapper import map_employee
from app.models.birthday_order import BirthdayOrder


def run() -> dict:
    client = get_employee_source()
    db = SessionLocal()

    updated = 0
    skipped_already_current = 0
    skipped_no_bamboohr_number = 0
    failed_lookup: list[str] = []

    try:
        distinct_employee_ids = [
            row[0]
            for row in db.query(BirthdayOrder.employee_id).distinct().all()
        ]

        for employee_id in distinct_employee_ids:
            try:
                raw_employee = client.get_employee(employee_id)
            except EmployeeSourceFetchError as exc:
                failed_lookup.append(employee_id)
                print(f"  FAILED lookup for employee_id={employee_id}: {exc}")
                continue

            if raw_employee is None:
                failed_lookup.append(employee_id)
                print(f"  NOT FOUND in BambooHR: employee_id={employee_id}")
                continue

            mapped = map_employee(raw_employee)
            fresh_number = mapped.get("employee_number")

            if not fresh_number:
                skipped_no_bamboohr_number += 1
                continue

            orders = db.query(BirthdayOrder).filter(BirthdayOrder.employee_id == employee_id).all()
            changed_any = False
            for order in orders:
                if order.employee_number == fresh_number:
                    continue
                order.employee_number = fresh_number
                changed_any = True

            if changed_any:
                updated += len(orders)
            else:
                skipped_already_current += len(orders)

        db.commit()
    finally:
        db.close()

    summary = {
        "updated": updated,
        "skipped_already_current": skipped_already_current,
        "skipped_no_bamboohr_number": skipped_no_bamboohr_number,
        "failed_lookup": failed_lookup,
    }
    print("Backfill complete:", summary)
    return summary


if __name__ == "__main__":
    run()
