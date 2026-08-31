"""RecruitmentSyncService — the DijiOne standard source-sync lifecycle for
Lever: single-flight, async reconciliation (scheduled + ad-hoc), durable
sync-run state, freshness. Lever is GET-only.

Reconciliation = posting sync + candidacy sync. It never touches
DijiTalentFlow's trust/visibility state — the governed DTC tag is exposed
on the posting DTO as a *fact* and resolved to a client by TalentFlow,
separately.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import MODULE_TALENT_FLOW, TA_MANAGER_ROLE, NotificationType
from app.db.session import SessionLocal
from app.models.sync_run import (
    ACTIVE_STATUSES,
    RecruitmentSyncRun,
    SyncStatus,
    SyncTriggerType,
)
from app.services import platform_notify
from app.services.lever_candidacy_sync_service import LeverCandidacySyncService
from app.services.lever_posting_service import LeverPostingSyncService

logger = logging.getLogger("recruitment-api.sync")


class RecruitmentSyncService:
    def __init__(self, db: Session):
        self.db = db

    # --- reads ---------------------------------------------------------

    def latest(self) -> RecruitmentSyncRun | None:
        return self.db.execute(
            select(RecruitmentSyncRun).order_by(RecruitmentSyncRun.requested_at.desc()).limit(1)
        ).scalars().first()

    def get(self, run_id: str) -> RecruitmentSyncRun | None:
        return self.db.execute(
            select(RecruitmentSyncRun).where(RecruitmentSyncRun.run_id == run_id)
        ).scalars().first()

    def history(self, limit: int = 20) -> list[RecruitmentSyncRun]:
        return list(
            self.db.execute(
                select(RecruitmentSyncRun)
                .order_by(RecruitmentSyncRun.requested_at.desc())
                .limit(limit)
            ).scalars().all()
        )

    def _active_run(self) -> RecruitmentSyncRun | None:
        return self.db.execute(
            select(RecruitmentSyncRun)
            .where(RecruitmentSyncRun.status.in_([s.value for s in ACTIVE_STATUSES]))
            .order_by(RecruitmentSyncRun.requested_at.desc())
            .limit(1)
        ).scalars().first()

    def last_successful_at(self) -> datetime | None:
        run = self.db.execute(
            select(RecruitmentSyncRun)
            .where(
                RecruitmentSyncRun.status.in_(
                    [SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value]
                )
            )
            .order_by(RecruitmentSyncRun.completed_at.desc())
            .limit(1)
        ).scalars().first()
        return run.completed_at if run else None

    def freshness(self) -> dict:
        latest = self.latest()
        return {
            "provider": "LEVER",
            "last_successful_sync_at": _iso(self.last_successful_at()),
            "latest_run": run_dto(latest) if latest else None,
        }

    # --- request (single-flight) ------------------------------------

    def request_sync(
        self,
        *,
        trigger_type: SyncTriggerType,
        requested_by_application: str,
        requested_by_user_id: int | None = None,
    ) -> tuple[RecruitmentSyncRun, bool]:
        existing = self._active_run()
        if existing is not None:
            return existing, False

        run = RecruitmentSyncRun(
            run_id=str(uuid.uuid4()),
            provider="LEVER",
            trigger_type=trigger_type.value,
            requested_by_application=requested_by_application,
            requested_by_user_id=requested_by_user_id,
            correlation_id=uuid.uuid4().hex[:16],
            status=SyncStatus.QUEUED.value,
        )
        self.db.add(run)
        self.db.commit()
        return run, True

    # --- execution (background task, own session) -------------------

    @staticmethod
    def execute_run(run_id: str) -> None:
        db = SessionLocal()
        try:
            svc = RecruitmentSyncService(db)
            run = svc.get(run_id)
            if run is None or run.status != SyncStatus.QUEUED.value:
                return
            run.status = SyncStatus.RUNNING.value
            run.started_at = datetime.now(UTC)
            db.commit()

            limit = get_settings().opportunity_sync_limit
            read = created = updated = unchanged = 0
            error: str | None = None
            try:
                p = LeverPostingSyncService(db).sync_postings()
                o = LeverCandidacySyncService(db).sync_opportunities(limit=limit)
                db.commit()
                read += int(p.get("total", 0))
                created += int(p.get("created", 0))
                updated += int(p.get("updated", 0))
                read += int(o.get("candidates_created", 0)) + int(o.get("candidates_matched", 0))
                created += int(o.get("candidates_created", 0)) + int(o.get("candidacies_created", 0))
                updated += int(o.get("candidacies_updated", 0))
                unchanged += int(o.get("candidates_matched", 0)) + int(
                    o.get("skipped_no_local_posting", 0)
                )
            except Exception as exc:  # noqa: BLE001 - record, never crash the worker
                db.rollback()
                error = _safe_error(exc)
                logger.warning("recruitment sync run %s failed: %s", run_id, error)

            run = svc.get(run_id)
            run.completed_at = datetime.now(UTC)
            run.records_read = read
            run.records_created = created
            run.records_updated = updated
            run.records_unchanged = unchanged
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


def run_dto(run: RecruitmentSyncRun) -> dict:
    return {
        "run_id": run.run_id,
        "provider": run.provider,
        "status": run.status,
        "trigger_type": run.trigger_type,
        "requested_by_application": run.requested_by_application,
        "requested_at": _iso(run.requested_at),
        "started_at": _iso(run.started_at),
        "completed_at": _iso(run.completed_at),
        "records_read": run.records_read,
        "records_created": run.records_created,
        "records_updated": run.records_updated,
        "records_unchanged": run.records_unchanged,
        "error_summary": run.error_summary,
    }


def _notify_completion(run: RecruitmentSyncRun) -> None:
    """Ad-hoc runs notify the requester. Scheduled successes are silent; a
    scheduled failure is an operational concern surfaced to TA_MANAGER."""
    ok = run.status in (SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value)
    if run.trigger_type == SyncTriggerType.AD_HOC.value and run.requested_by_user_id:
        platform_notify.notify_user(
            user_id=run.requested_by_user_id,
            type=(
                NotificationType.RECRUITMENT_SYNC_COMPLETE.value
                if ok
                else NotificationType.INTEGRATION_SYNC_FAILED.value
            ),
            title="Recruitment data synced" if ok else "Recruitment sync failed",
            body=(
                f"{run.records_read} records checked · "
                f"{run.records_created} new, {run.records_updated} updated."
                if ok
                else "Please try again shortly."
            ),
            related_entity_id=run.id,
        )
    elif run.trigger_type == SyncTriggerType.SCHEDULED.value and not ok:
        platform_notify.notify_module_role(
            module_key=MODULE_TALENT_FLOW,
            role=TA_MANAGER_ROLE,
            type=NotificationType.INTEGRATION_SYNC_FAILED.value,
            title="Scheduled recruitment sync failed",
            body="The 6-hourly Lever reconciliation did not complete.",
            related_entity_id=run.id,
        )
