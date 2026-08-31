"""RecruitmentSyncService — the standard DijiOne source-sync lifecycle for
Lever: single-flight, async reconciliation (scheduled + ad-hoc), durable
sync-run state, freshness.

Reconciliation reuses the existing, unchanged Lever adapters
(LeverPostingSyncService, LeverContactApplicationSyncService) — this is a
*move behind a boundary*, not a rewrite. Lever remains GET-only.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.recruitment_source.models import (
    ACTIVE_STATUSES,
    RecruitmentSyncRun,
    SyncStatus,
    SyncTriggerType,
)
from app.services.lever_contact_application_sync_service import LeverContactApplicationSyncService
from app.services.lever_posting_service import LeverPostingSyncService

logger = logging.getLogger("talent-api.recruitment_source")

# A tenant can have very large opportunity counts — the reconciliation pull
# is deliberately bounded per run (CLAUDE.md §60 "minimum reasonable requests").
_OPPORTUNITY_LIMIT = 200


class SyncService:
    def __init__(self, db: Session):
        self.db = db

    # --- reads -----------------------------------------------------------

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
            .where(RecruitmentSyncRun.status.in_([SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value]))
            .order_by(RecruitmentSyncRun.completed_at.desc())
            .limit(1)
        ).scalars().first()
        return run.completed_at if run else None

    def freshness(self) -> dict:
        latest = self.latest()
        return {
            "provider": "LEVER",
            "last_successful_sync_at": _iso(self.last_successful_at()),
            "latest_run": _run_dto(latest) if latest else None,
        }

    # --- request (single-flight) --------------------------------------

    def request_sync(
        self,
        *,
        trigger_type: SyncTriggerType,
        requested_by_application: str,
        requested_by_user_id: int | None = None,
    ) -> tuple[RecruitmentSyncRun, bool]:
        """Returns (run, started). ``started`` is False when an ACTIVE run
        already exists — the caller is coalesced onto it (no thundering herd
        of provider calls)."""
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

    # --- execution (runs in a background task, own session) -------------

    @staticmethod
    def execute_run(run_id: str) -> None:
        db = SessionLocal()
        try:
            svc = SyncService(db)
            run = svc.get(run_id)
            if run is None or run.status != SyncStatus.QUEUED.value:
                return
            run.status = SyncStatus.RUNNING.value
            run.started_at = datetime.now(UTC)
            db.commit()

            read = created = updated = unchanged = 0
            error: str | None = None
            try:
                p = LeverPostingSyncService(db).sync_postings()
                o = LeverContactApplicationSyncService(db).sync_opportunities(
                    limit=_OPPORTUNITY_LIMIT
                )
                # Governed DTC posting-tag -> PostingClientMapping reconciliation
                # (TalentFlow trust decision, runs on every scheduled + ad-hoc sync).
                from app.services.posting_client_mapping_reconciler import (
                    PostingClientMappingReconciler,
                )

                dtc = PostingClientMappingReconciler(db).reconcile_all()
                db.commit()
                # postings: {created, updated, total}
                read += int(p.get("total", 0))
                created += int(p.get("created", 0))
                updated += int(p.get("updated", 0))
                # opportunities/candidates: {candidates_created, candidates_matched,
                #   posting_applications_created, posting_applications_updated,
                #   skipped_no_local_posting}
                read += int(o.get("candidates_created", 0)) + int(o.get("candidates_matched", 0))
                created += int(o.get("candidates_created", 0)) + int(
                    o.get("posting_applications_created", 0)
                )
                updated += int(o.get("posting_applications_updated", 0))
                unchanged += int(o.get("candidates_matched", 0)) + int(
                    o.get("skipped_no_local_posting", 0)
                )
                # DTC reconciliation counts
                updated += dtc.resolved + dtc.reassigned + dtc.reverted + dtc.conflicts
                unchanged += dtc.unchanged + dtc.no_tag + dtc.unknown + dtc.ambiguous + dtc.malformed
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
            run.status = (
                SyncStatus.FAILED.value if error else SyncStatus.SUCCEEDED.value
            )
            db.commit()

            _notify_completion(run)
        finally:
            db.close()


def _safe_error(exc: Exception) -> str:
    # Never surface a URL/secret/credential — class + short message only.
    msg = str(exc).splitlines()[0][:200] if str(exc) else exc.__class__.__name__
    return f"{exc.__class__.__name__}: {msg}"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _run_dto(run: RecruitmentSyncRun) -> dict:
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
    """Ad-hoc runs get a lightweight notification to the requester.
    Scheduled runs update freshness silently (a scheduled *failure* is an
    operational concern, surfaced to TA_MANAGER)."""
    try:
        from app.core.constants import MODULE_TALENT_FLOW, NotificationType, TalentFlowRole
        from app.services.notification_service import NotificationService

        notifications = NotificationService()
        ok = run.status in (SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value)

        if run.trigger_type == SyncTriggerType.AD_HOC.value and run.requested_by_user_id:
            notifications.notify_user(
                user_id=run.requested_by_user_id,
                type=NotificationType.INTEGRATION_SYNC_FAILED.value
                if not ok
                else "RECRUITMENT_SYNC_COMPLETE",
                title="Recruitment data synced"
                if ok
                else "Recruitment sync failed",
                body=(
                    f"{run.records_read} records checked · "
                    f"{run.records_created} new, {run.records_updated} updated."
                    if ok
                    else "Please try again shortly."
                ),
                related_entity_type="RecruitmentSyncRun",
                related_entity_id=run.id,
            )
        elif run.trigger_type == SyncTriggerType.SCHEDULED.value and not ok:
            notifications.notify_module_role(
                module_key=MODULE_TALENT_FLOW,
                role=TalentFlowRole.TA_MANAGER.value,
                type=NotificationType.INTEGRATION_SYNC_FAILED.value,
                title="Scheduled recruitment sync failed",
                body="The 6-hourly Lever reconciliation did not complete.",
                related_entity_type="RecruitmentSyncRun",
                related_entity_id=run.id,
            )
    except Exception:  # noqa: BLE001 - notifications are best-effort
        logger.debug("recruitment sync completion notification skipped", exc_info=True)
