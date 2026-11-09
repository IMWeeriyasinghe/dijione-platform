"""RecruitmentSyncService — the DijiOne standard source-sync lifecycle for
Lever: single-flight, async reconciliation (scheduled + ad-hoc), durable
sync-run state, freshness. Lever is GET-only.

Reconciliation = posting sync + candidacy sync. It never touches
DijiTalentFlow's trust/visibility state — the governed DTC tag is exposed
on the posting DTO as a *fact* and resolved to a client by TalentFlow,
separately.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import MODULE_TALENT_FLOW, TA_MANAGER_ROLE, NotificationType
from app.db.session import SessionLocal
from app.models.sync_run import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    RecruitmentSyncRun,
    SyncStatus,
    SyncTriggerType,
)
from app.repositories.posting_repo import PostingRepository
from app.services import platform_notify
from app.services.lever_candidacy_sync_service import (
    SNAPSHOT_MAX_AGE,
    LeverCandidacySyncService,
    dtc_postings,
    unread_postings,
)
from app.services.lever_posting_service import LeverPostingSyncService

logger = logging.getLogger("recruitment-api.sync")

# A live run touches its row every heartbeat, however slow Lever is. Silence for
# this long means its replica has gone.
_HEARTBEAT_SECONDS = 30.0
_ABANDONED_AFTER = timedelta(minutes=10)
# Serializes the "is one active? then create" check across replicas (PostgreSQL).
_SYNC_REQUEST_LOCK = 7206114


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
        runs = self.db.execute(
            select(RecruitmentSyncRun)
            .where(RecruitmentSyncRun.status.in_([s.value for s in ACTIVE_STATUSES]))
            .order_by(RecruitmentSyncRun.requested_at.desc())
            .with_for_update()  # a run finishing right now must not then be abandoned
        ).scalars().all()
        now = datetime.now(UTC)
        active = [r for r in runs if not self._abandon_if_stale(r, now)]
        return active[0] if active else None

    def _abandon_if_stale(self, run: RecruitmentSyncRun, now: datetime) -> bool:
        last_seen = run.updated_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=UTC)
        if now - last_seen < _ABANDONED_AFTER:
            return False
        run.status = SyncStatus.FAILED.value
        run.completed_at = now
        run.error_summary = "Abandoned: the run did not record a result."
        self.db.flush()
        logger.warning("recruitment sync run %s abandoned", run.run_id)
        return True

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
            "source_snapshot": self.source_snapshot(),
        }

    def source_snapshot(self) -> dict:
        """Whether consumers may treat the client-posting data as a full read."""
        now = datetime.now(UTC)
        postings = dtc_postings(PostingRepository(self.db))
        unread = len(unread_postings(postings, now))
        runs = self.db.execute(
            select(RecruitmentSyncRun).order_by(RecruitmentSyncRun.requested_at.desc()).limit(20)
        ).scalars().all()
        terminal = [r for r in runs if r.status in {s.value for s in TERMINAL_STATUSES}]
        if any(r.status in {s.value for s in ACTIVE_STATUSES} for r in runs):
            state = "RUNNING"
        elif not terminal or terminal[0].completed_at is None:
            state = "NONE"
        elif terminal[0].status == SyncStatus.FAILED.value:
            state = "FAILED"
        elif now - _utc(terminal[0].completed_at) >= SNAPSHOT_MAX_AGE:
            state = "STALE"
        else:
            state = "COMPLETE" if postings and not unread and _general_read_finished(terminal[0]) else "INCOMPLETE"
        return {
            "state": state,
            "client_postings_total": len(postings),
            "client_postings_unread": unread,
            "latest_run_status": terminal[0].status if terminal else None,
        }

    # --- request (single-flight) ------------------------------------

    def request_sync(
        self,
        *,
        trigger_type: SyncTriggerType,
        requested_by_application: str,
        requested_by_user_id: int | None = None,
    ) -> tuple[RecruitmentSyncRun, bool]:
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SYNC_REQUEST_LOCK})
        existing = self._active_run()
        if existing is not None:
            self.db.commit()
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
            heartbeat_stop = threading.Event()
            threading.Thread(target=_heartbeat, args=(run_id, heartbeat_stop), daemon=True).start()

            limit = get_settings().opportunity_sync_limit
            read = created = updated = unchanged = 0
            error: str | None = None
            incomplete: str | None = None
            detail: dict | None = None
            try:
                p = LeverPostingSyncService(db).sync_postings()
                o = LeverCandidacySyncService(db).sync_opportunities(limit=limit)
                db.commit()
                posting_reads, posting_total = o.get("dtc_postings_read", 0), o.get("dtc_postings_total", 0)
                failed, deferred = o.get("dtc_postings_failed", 0), o.get("dtc_postings_deferred", 0)
                already_current = o.get("dtc_postings_current", 0)
                if posting_reads + already_current < posting_total:
                    incomplete = f"Incomplete: {posting_reads} of {posting_total} client postings read."
                    if failed or deferred:
                        incomplete = f"{incomplete[:-1]}; {failed} failed, {deferred} deferred."
                elif o.get("general_budget_exhausted"):
                    incomplete = "Incomplete: the general opportunity read stopped at its budget."
                detail = {
                    "postings": {k: int(p.get(k, 0)) for k in ("total", "created", "updated")},
                    "candidates": {k: int(o.get(f"candidates_{k}", 0)) for k in ("created", "matched")},
                    "candidacies": {k: int(o.get(f"candidacies_{k}", 0)) for k in ("created", "updated")},
                    "client_postings": {
                        "total": posting_total, "processed": posting_reads, "current": already_current, "failed": failed,
                        "deferred": deferred, "remaining": o.get("dtc_postings_remaining", 0),
                    },
                    "opportunities_seen": o.get("opportunities_seen", 0),
                    "general_budget_exhausted": bool(o.get("general_budget_exhausted")),
                }
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

            heartbeat_stop.set()
            # Locked and re-read: another replica may have just abandoned this run.
            run = db.execute(
                select(RecruitmentSyncRun)
                .where(RecruitmentSyncRun.run_id == run_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).scalars().one()
            if run.status != SyncStatus.RUNNING.value:
                db.rollback()
                logger.warning("recruitment sync run %s finished after being abandoned", run_id)
                return
            run.completed_at = datetime.now(UTC)
            run.records_read = read
            run.records_created = created
            run.records_updated = updated
            run.records_unchanged = unchanged
            run.error_summary = error or incomplete
            run.detail = json.dumps(detail) if detail else None
            if error:
                run.status = SyncStatus.FAILED.value
            elif incomplete:
                run.status = SyncStatus.PARTIAL.value
            else:
                run.status = SyncStatus.SUCCEEDED.value
            db.commit()

            _notify_completion(run)
        finally:
            db.close()


def _heartbeat(run_id: str, stop: threading.Event) -> None:
    """Uses its own session: the run's transaction stays open until it finishes."""
    while not stop.wait(_HEARTBEAT_SECONDS):
        db = SessionLocal()
        try:
            db.execute(
                update(RecruitmentSyncRun)
                .where(
                    RecruitmentSyncRun.run_id == run_id,
                    RecruitmentSyncRun.status == SyncStatus.RUNNING.value,
                )
                .values(updated_at=datetime.now(UTC))
            )
            db.commit()
        except Exception:  # noqa: BLE001 - a missed beat must not stop the sync
            db.rollback()
            logger.warning("recruitment sync run %s heartbeat failed", run_id)
        finally:
            db.close()


def _safe_error(exc: Exception) -> str:
    msg = str(exc).splitlines()[0][:200] if str(exc) else exc.__class__.__name__
    return f"{exc.__class__.__name__}: {msg}"


def _general_read_finished(run: RecruitmentSyncRun) -> bool:
    """A run without recorded detail proves nothing about what it read."""
    if not run.detail:
        return False
    return not json.loads(run.detail).get("general_budget_exhausted", True)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


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
        "detail": json.loads(run.detail) if run.detail else None,
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
    elif run.trigger_type == SyncTriggerType.SCHEDULED.value and run.status != SyncStatus.SUCCEEDED.value:
        platform_notify.notify_module_role(
            module_key=MODULE_TALENT_FLOW,
            role=TA_MANAGER_ROLE,
            type=NotificationType.INTEGRATION_SYNC_FAILED.value,
            title="Scheduled recruitment sync failed",
            body="The 6-hourly Lever reconciliation did not complete.",
            related_entity_id=run.id,
        )
