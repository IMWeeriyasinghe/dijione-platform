"""Read-only ingestion of BambooHR's active-employee directory into the
durable Employee read model.

    BambooHR (Custom Report API, GET-shaped) -> BambooHRClient ->
    BambooHREmployee -> map_employee -> Employee

Never writes to BambooHR. This is the read model that did not exist before
Wave E — birthday-api previously made a live call per request with nothing
persisted.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.integrations.bamboohr.mapper import map_employee
from app.integrations.factory import get_bamboohr_client
from app.repositories.employee_repo import EmployeeRepository

logger = logging.getLogger("people-api.employee_sync")


class EmployeeSyncService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = EmployeeRepository(db)

    def sync_employees(self) -> dict:
        client = get_bamboohr_client()
        raw_employees = client.list_active_employees()

        created = 0
        updated = 0
        now = datetime.now(UTC)
        for raw in raw_employees:
            mapped = map_employee(raw)
            fields = {
                "employee_number": mapped.get("employee_number"),
                "full_name": mapped["full_name"],
                "work_email": mapped["work_email"],
                "birth_month": mapped["birth_month"],
                "birth_day": mapped["birth_day"],
                "department": mapped.get("department") or "",
                "office_location": mapped["office_location"],
                "employment_status": mapped["employment_status"],
                "hire_date": mapped.get("hire_date"),
                "termination_date": mapped.get("termination_date"),
                "address_line1": mapped.get("address_line1"),
                "address_line2": mapped.get("address_line2"),
                "city": mapped.get("city"),
                "state_province": mapped.get("state_province"),
                "postal_code": mapped.get("postal_code"),
                "country": mapped.get("country"),
                "last_synced_at": now,
            }
            _row, is_new = self.repo.upsert(mapped["employee_id"], fields)
            created += int(is_new)
            updated += int(not is_new)

        self.db.flush()
        logger.info(
            "BambooHR employee sync: created=%s updated=%s total=%s",
            created, updated, len(raw_employees),
        )
        return {"created": created, "updated": updated, "total": len(raw_employees)}
