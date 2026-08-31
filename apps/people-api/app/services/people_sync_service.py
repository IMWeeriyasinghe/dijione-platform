"""PeopleSyncService — the DijiOne standard source-sync lifecycle for
BambooHR: single-flight, async reconciliation (scheduled + ad-hoc), durable
sync-run state, freshness.

Frequency is People's own approved cadence (daily), not Lever's 6h — the
standard's *shape* (single-flight, async 202, durable run state,
idempotent, retain-last-good-on-failure, scheduled-silent /
ad-hoc-notified) is what's shared, not the interval.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    ACTIVE_STATUSES,
    BIRTHDAY_ADMIN_ROLE,
    MODULE_BIRTHDAY,
    NotificationType,
    SyncStatus,
    SyncTriggerType,
)
from app.db.session import SessionLocal
from app.models.sync_run import PeopleSyncRun
from app.services import platform_notify
from app.services.employee_sync_service import EmployeeSyncService

logger = logging.getLogger("people-api.sync")


class PeopleSyncService:
    def __init__(self, db: Session):
        self.db = db

    def latest(self) -> PeopleSyncRun | None:
        return self.db.execute(
            select(PeopleSyncRun).order_by(PeopleSyncRun.requested_at.desc()).limit(1)
        ).scalars().first()

    def get(self, run_id: str) -> PeopleSyncRun | None:
        return self.db.execute(
            select(PeopleSyncRun).where(PeopleSyncRun.run_id == run_id)
        ).scalars().first()

    def history(self, limit: int = 20) -> list[PeopleSyncRun]:
        return list(
            self.db.execute(
                select(PeopleSyncRun).order_by(PeopleSyncRun.requested_at.desc()).limit(limit)
            ).scalars().all()
        )

    def _active_run(self) -> PeopleSyncRun | None:
        return self.db.execute(
            select(PeopleSyncRun)
            .where(PeopleSyncRun.status.in_([s.value for s in ACTIVE_STATUSES]))
            .order_by(PeopleSyncRun.requested_at.desc())
            .limit(1)
        ).scalars().first()

    def last_successful_at(self) -> datetime | None:
        run = self.db.execute(
            select(PeopleSyncRun)
            .where(PeopleSyncRun.status.in_([SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value]))
            .order_by(PeopleSyncRun.completed_at.desc())
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
    ) -> tuple[PeopleSyncRun, bool]:
        existing = self._active_run()
        if existing is not None:
            return existing, False
        run = PeopleSyncRun(
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
            svc = PeopleSyncService(db)
            run = svc.get(run_id)
            if run is None or run.status != SyncStatus.QUEUED.value:
                return
            run.status = SyncStatus.RUNNING.value
            run.started_at = datetime.now(UTC)
            db.commit()

            read = created = updated = 0
            error: str | None = None
            try:
                result = EmployeeSyncService(db).sync_employees()
                db.commit()
                read = int(result.get("total", 0))
                created = int(result.get("created", 0))
                updated = int(result.get("updated", 0))
            except Exception as exc:  # noqa: BLE001 - record, never crash the worker
                db.rollback()
                error = _safe_error(exc)
                logger.warning("people sync run %s failed: %s", run_id, error)

            run = svc.get(run_id)
            run.completed_at = datetime.now(UTC)
            run.records_read = read
            run.records_created = created
            run.records_updated = updated
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


def run_dto(run: PeopleSyncRun) -> dict:
    return {
        "run_id": run.run_id, "provider": run.provider, "status": run.status,
        "trigger_type": run.trigger_type, "requested_by_application": run.requested_by_application,
        "requested_at": _iso(run.requested_at), "started_at": _iso(run.started_at),
        "completed_at": _iso(run.completed_at), "records_read": run.records_read,
        "records_created": run.records_created, "records_updated": run.records_updated,
        "records_unchanged": run.records_unchanged, "error_summary": run.error_summary,
    }


def _notify_completion(run: PeopleSyncRun) -> None:
    ok = run.status in (SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value)
    if run.trigger_type == SyncTriggerType.AD_HOC.value and run.requested_by_user_id:
        platform_notify.notify_user(
            user_id=run.requested_by_user_id,
            type=NotificationType.PEOPLE_SYNC_COMPLETE.value if ok else NotificationType.INTEGRATION_SYNC_FAILED.value,
            title="Employee directory synced" if ok else "Employee directory sync failed",
            body=(
                f"{run.records_read} employees checked · {run.records_created} new, "
                f"{run.records_updated} updated." if ok else "Please try again shortly."
            ),
            related_entity_id=run.id,
        )
    elif run.trigger_type == SyncTriggerType.SCHEDULED.value and not ok:
        platform_notify.notify_module_role(
            module_key=MODULE_BIRTHDAY, role=BIRTHDAY_ADMIN_ROLE,
            type=NotificationType.INTEGRATION_SYNC_FAILED.value,
            title="Scheduled employee directory sync failed",
            body="The daily BambooHR reconciliation did not complete.",
            related_entity_id=run.id,
        )
