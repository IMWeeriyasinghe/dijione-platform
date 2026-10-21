"""WorkforceSyncService — the DijiOne standard source-sync lifecycle
(CLAUDE.md rules 10–17) for the generic Workforce Directory: single-flight,
async reconciliation (scheduled + ad-hoc), durable run state, freshness.

Entirely separate from ``PeopleSyncService`` / ``EmployeeSyncService`` (the
Birthday-oriented Employee contract): its own provider client, its own
tables, its own runs. A workforce run never reads or writes ``employees``
or ``people_sync_runs``.

    BambooHR (Custom Report, read-only) -> BambooHRWorkforceClient ->
    BambooHRWorkforceRecord -> map_workforce_record -> WorkforceDirectoryEntry
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import ACTIVE_STATUSES, NotificationType, SyncStatus, SyncTriggerType
from app.db.session import SessionLocal
from app.integrations.bamboohr.workforce_mapper import map_workforce_record
from app.integrations.factory import get_bamboohr_workforce_client
from app.models.workforce import WorkforceDirectoryEntry, WorkforceSyncRun
from app.services import platform_notify

logger = logging.getLogger("people-api.workforce_sync")

_TRACKED_FIELDS = (
    "employee_number", "display_name", "department", "job_title", "location",
    "employment_status", "hire_date", "termination_date",
)


class WorkforceDirectoryService:
    """Reconciles the directory from one full provider read. Idempotent:
    insert new, update changed, keep stable ids; never deletes."""

    def __init__(self, db: Session):
        self.db = db

    def list_entries(self, status: str = "all") -> list[WorkforceDirectoryEntry]:
        stmt = select(WorkforceDirectoryEntry).order_by(WorkforceDirectoryEntry.display_name)
        if status == "active":
            stmt = stmt.where(WorkforceDirectoryEntry.employment_status == "Active")
        elif status == "inactive":
            stmt = stmt.where(WorkforceDirectoryEntry.employment_status != "Active")
        return list(self.db.execute(stmt).scalars().all())

    def reconcile(self) -> dict:
        records = get_bamboohr_workforce_client().list_workforce_records()
        now = datetime.now(UTC)
        existing = {
            e.bamboohr_id: e for e in self.db.execute(select(WorkforceDirectoryEntry)).scalars().all()
        }

        created = updated = unchanged = 0
        seen: set[str] = set()
        for record in records:
            mapped = map_workforce_record(record)
            bamboohr_id = mapped.pop("bamboohr_id")
            seen.add(bamboohr_id)
            row = existing.get(bamboohr_id)
            if row is None:
                self.db.add(WorkforceDirectoryEntry(
                    bamboohr_id=bamboohr_id, present_in_source=True,
                    first_synced_at=now, last_synced_at=now, **mapped,
                ))
                created += 1
                continue
            changed = not row.present_in_source or any(
                getattr(row, f) != mapped[f] for f in _TRACKED_FIELDS
            )
            for field in _TRACKED_FIELDS:
                setattr(row, field, mapped[field])
            row.present_in_source = True
            row.last_synced_at = now
            updated += int(changed)
            unchanged += int(not changed)

        absent = 0
        for bamboohr_id, row in existing.items():
            if bamboohr_id not in seen and row.present_in_source:
                row.present_in_source = False
                absent += 1

        self.db.flush()
        logger.info(
            "Workforce directory sync: created=%s updated=%s unchanged=%s absent=%s total=%s",
            created, updated, unchanged, absent, len(records),
        )
        return {
            "total": len(records), "created": created, "updated": updated,
            "unchanged": unchanged, "absent": absent,
        }


class WorkforceSyncService:
    def __init__(self, db: Session):
        self.db = db

    def latest(self) -> WorkforceSyncRun | None:
        return self.db.execute(
            select(WorkforceSyncRun).order_by(WorkforceSyncRun.requested_at.desc()).limit(1)
        ).scalars().first()

    def get(self, run_id: str) -> WorkforceSyncRun | None:
        return self.db.execute(
            select(WorkforceSyncRun).where(WorkforceSyncRun.run_id == run_id)
        ).scalars().first()

    def history(self, limit: int = 20) -> list[WorkforceSyncRun]:
        return list(
            self.db.execute(
                select(WorkforceSyncRun).order_by(WorkforceSyncRun.requested_at.desc()).limit(limit)
            ).scalars().all()
        )

    def _active_run(self) -> WorkforceSyncRun | None:
        return self.db.execute(
            select(WorkforceSyncRun)
            .where(WorkforceSyncRun.status.in_([s.value for s in ACTIVE_STATUSES]))
            .order_by(WorkforceSyncRun.requested_at.desc())
            .limit(1)
        ).scalars().first()

    def last_successful_at(self) -> datetime | None:
        run = self.db.execute(
            select(WorkforceSyncRun)
            .where(WorkforceSyncRun.status.in_([SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value]))
            .order_by(WorkforceSyncRun.completed_at.desc())
            .limit(1)
        ).scalars().first()
        return run.completed_at if run else None

    def freshness(self) -> dict:
        latest = self.latest()
        return {
            "provider": "BAMBOOHR",
            "last_successful_sync_at": _iso(self.last_successful_at()),
            "latest_run": run_dto(latest) if latest else None,
        }

    def request_sync(
        self, *, trigger_type: SyncTriggerType, requested_by_application: str,
        requested_by_user_id: int | None = None,
    ) -> tuple[WorkforceSyncRun, bool]:
        existing = self._active_run()
        if existing is not None:
            return existing, False
        run = WorkforceSyncRun(
            run_id=str(uuid.uuid4()), provider="BAMBOOHR", trigger_type=trigger_type.value,
            requested_by_application=requested_by_application,
            requested_by_user_id=requested_by_user_id, correlation_id=uuid.uuid4().hex[:16],
            status=SyncStatus.QUEUED.value,
        )
        self.db.add(run)
        self.db.commit()
        return run, True

    @staticmethod
    def execute_run(run_id: str) -> None:
        db = SessionLocal()
        try:
            svc = WorkforceSyncService(db)
            run = svc.get(run_id)
            if run is None or run.status != SyncStatus.QUEUED.value:
                return
            run.status = SyncStatus.RUNNING.value
            run.started_at = datetime.now(UTC)
            db.commit()

            result: dict = {}
            error: str | None = None
            try:
                result = WorkforceDirectoryService(db).reconcile()
                db.commit()
            except Exception as exc:  # noqa: BLE001 - record, never crash the worker
                db.rollback()  # previous directory stays intact (rule 15)
                error = _safe_error(exc)
                logger.warning("workforce sync run %s failed: %s", run_id, error)

            run = svc.get(run_id)
            run.completed_at = datetime.now(UTC)
            run.records_read = int(result.get("total", 0))
            run.records_created = int(result.get("created", 0))
            run.records_updated = int(result.get("updated", 0))
            run.records_unchanged = int(result.get("unchanged", 0))
            run.records_absent = int(result.get("absent", 0))
            run.error_summary = error
            run.status = SyncStatus.FAILED.value if error else SyncStatus.SUCCEEDED.value
            db.commit()

            _notify_completion(run)
        finally:
            db.close()


def _safe_error(exc: Exception) -> str:
    msg = str(exc).splitlines()[0][:200] if str(exc) else exc.__class__.__name__
    return f"{exc.__class__.__name__}: {msg}"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def run_dto(run: WorkforceSyncRun) -> dict:
    return {
        "run_id": run.run_id, "provider": run.provider, "status": run.status,
        "trigger_type": run.trigger_type, "requested_by_application": run.requested_by_application,
        "requested_at": _iso(run.requested_at), "started_at": _iso(run.started_at),
        "completed_at": _iso(run.completed_at), "records_read": run.records_read,
        "records_created": run.records_created, "records_updated": run.records_updated,
        "records_unchanged": run.records_unchanged, "records_absent": run.records_absent,
        "error_summary": run.error_summary,
    }


def _notify_completion(run: WorkforceSyncRun) -> None:
    """Ad-hoc runs notify the requesting user (best effort). Scheduled
    failures are logged only: the directory is a generic capability with no
    owning application role to broadcast to."""
    ok = run.status in (SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value)
    if run.trigger_type == SyncTriggerType.AD_HOC.value and run.requested_by_user_id:
        platform_notify.notify_user(
            user_id=run.requested_by_user_id,
            type=NotificationType.PEOPLE_SYNC_COMPLETE.value if ok else NotificationType.INTEGRATION_SYNC_FAILED.value,
            title="Workforce directory synced" if ok else "Workforce directory sync failed",
            body=(
                f"{run.records_read} records checked · {run.records_created} new, "
                f"{run.records_updated} updated." if ok else "Please try again shortly."
            ),
        )
    elif not ok:
        logger.warning("scheduled workforce directory sync %s failed: %s", run.run_id, run.error_summary)
