"""Incremental raw-event mirror: Azure SQL ``onsite.*`` -> ``onsite_<env>``.

CLAUDE.md source-sync lifecycle: single-flight, asynchronous (202 +
run_id), durable run state, idempotent, a failed run keeps the previous
mirror intact. Never deletes mirrored rows.

Algorithm:
1. Discover sites (safe columns); a new site gets ``site_settings.enabled =
   False`` — existing settings are never changed by a sync.
2. Keyset pages of ``sync_page_size`` ordered by (ReceivedUtc, EventId),
   starting at (high-water mark − ``sync_overlap_minutes``); insert only
   EventIds not already mirrored; commit per page; advance the high-water mark.
3. Replace the agent-status snapshot.
4. Reconcile source vs mirror per (SiteId, SourceEpoch) and record drift.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.attendance_source.client import SourceUnavailableError
from app.attendance_source.factory import get_onsite_source
from app.core.config import get_settings
from app.core.constants import ACTIVE_STATUSES, SyncStatus, SyncTriggerType
from app.db.session import SessionLocal
from app.models.mirror import AgentStatus, AttendanceEvent, OnsiteSyncRun, SiteSettings, SourceSite, SyncState
from app.services.time_derivation import site_local_date, tz_consistent

logger = logging.getLogger("onsite-api.mirror_sync")


class MirrorSyncService:
    def __init__(self, db: Session):
        self.db = db

    # --- run lifecycle -------------------------------------------------------
    def get(self, run_id: str) -> OnsiteSyncRun | None:
        return self.db.execute(select(OnsiteSyncRun).where(OnsiteSyncRun.run_id == run_id)).scalars().first()

    def latest(self) -> OnsiteSyncRun | None:
        return self.db.execute(
            select(OnsiteSyncRun).order_by(OnsiteSyncRun.requested_at.desc(), OnsiteSyncRun.id.desc()).limit(1)
        ).scalars().first()

    def last_successful(self) -> OnsiteSyncRun | None:
        return self.db.execute(
            select(OnsiteSyncRun)
            .where(OnsiteSyncRun.status.in_([SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value]))
            .order_by(OnsiteSyncRun.completed_at.desc(), OnsiteSyncRun.id.desc()).limit(1)
        ).scalars().first()

    def history(self, limit: int = 20) -> list[OnsiteSyncRun]:
        return list(self.db.execute(
            select(OnsiteSyncRun).order_by(OnsiteSyncRun.requested_at.desc(), OnsiteSyncRun.id.desc()).limit(limit)
        ).scalars())

    def request_sync(
        self, *, trigger_type: SyncTriggerType, requested_by_user_id: int | None = None
    ) -> tuple[OnsiteSyncRun, bool]:
        active = self.db.execute(
            select(OnsiteSyncRun).where(OnsiteSyncRun.status.in_([s.value for s in ACTIVE_STATUSES]))
            .order_by(OnsiteSyncRun.requested_at.desc()).limit(1)
        ).scalars().first()
        if active is not None:
            return active, False
        run = OnsiteSyncRun(
            run_id=str(uuid.uuid4()), trigger_type=trigger_type.value, requested_by_user_id=requested_by_user_id,
            correlation_id=uuid.uuid4().hex[:16], status=SyncStatus.QUEUED.value,
        )
        self.db.add(run)
        self.db.commit()
        return run, True

    @staticmethod
    def execute_run(run_id: str) -> None:
        db = SessionLocal()
        try:
            svc = MirrorSyncService(db)
            run = svc.get(run_id)
            if run is None or run.status != SyncStatus.QUEUED.value:
                return
            run.status = SyncStatus.RUNNING.value
            run.started_at = datetime.now(UTC)
            db.commit()
            svc._run(run)
        finally:
            db.close()

    def _run(self, run: OnsiteSyncRun) -> None:
        source = None
        error: str | None = None
        try:
            source = get_onsite_source()
            run.sites_discovered = self._discover_sites(source)
            self._mirror_events(source, run)
            self._snapshot_agent_status(source)
            run.reconciliation_json = json.dumps(self._reconcile(source), default=str)
        except SourceUnavailableError as exc:
            self.db.rollback()
            run.source_unavailable = True
            error = _safe_error(exc)
        except Exception as exc:  # noqa: BLE001 - record, never crash the worker
            self.db.rollback()
            error = _safe_error(exc)
        finally:
            if source is not None:
                source.close()
        run.completed_at = datetime.now(UTC)
        run.error_summary = error
        run.status = SyncStatus.FAILED.value if error else SyncStatus.SUCCEEDED.value
        self.db.commit()
        if error:
            logger.warning("onsite mirror sync %s failed: %s", run.run_id, error)

    # --- steps -------------------------------------------------------------
    def _discover_sites(self, source) -> int:
        now = datetime.now(UTC)
        sites = source.list_sites()
        for s in sites:
            row = self.db.get(SourceSite, s.site_id)
            if row is None:
                row = SourceSite(site_id=s.site_id)
                self.db.add(row)
            row.display_name, row.time_zone, row.is_active = s.display_name, s.time_zone, s.is_active
            row.created_utc, row.last_seen_at = s.created_utc, now
            exists = self.db.execute(select(SiteSettings.id).where(SiteSettings.site_id == s.site_id)).first()
            if exists is None:
                self.db.add(SiteSettings(site_id=s.site_id, enabled=False))
        self.db.commit()
        return len(sites)

    def _mirror_events(self, source, run: OnsiteSyncRun) -> None:
        settings = get_settings()
        state = self.db.get(SyncState, 1) or SyncState(id=1)
        self.db.add(state)
        hwm = state.high_water_received_utc
        cursor_received = hwm - timedelta(minutes=settings.sync_overlap_minutes) if hwm else None
        cursor_event = ""
        time_zones = {s.site_id: s.time_zone for s in self.db.execute(select(SourceSite)).scalars()}

        while True:
            page = source.read_events_after(cursor_received, cursor_event, settings.sync_page_size)
            if not page:
                break
            ids = [e.event_id for e in page]
            existing = set(self.db.execute(select(AttendanceEvent.event_id).where(AttendanceEvent.event_id.in_(ids))).scalars())
            now = datetime.now(UTC)
            for e in page:
                if e.event_id in existing:
                    continue
                self.db.add(AttendanceEvent(
                    event_id=e.event_id, site_id=e.site_id, source_epoch=e.source_epoch,
                    source_transaction_id=e.source_transaction_id, emp_code=e.emp_code, emp_id=e.emp_id,
                    punch_time_local=e.punch_time_local, punch_time_utc=e.punch_time_utc, time_zone=e.time_zone,
                    punch_state=e.punch_state, verify_type=e.verify_type, work_code=e.work_code,
                    terminal_sn=e.terminal_sn, terminal_alias=e.terminal_alias, area_alias=e.area_alias,
                    source=e.source, is_attendance=e.is_attendance, upload_time_utc=e.upload_time_utc,
                    captured_at_utc=e.captured_at_utc, received_utc=e.received_utc, batch_id=e.batch_id,
                    record_hash=e.record_hash,
                    site_local_date=site_local_date(e.punch_time_local),
                    tz_consistent=tz_consistent(e.punch_time_local, e.punch_time_utc, time_zones.get(e.site_id)),
                    sync_run_id=run.run_id, mirrored_at=now,
                ))
            run.events_read += len(page)
            run.events_inserted += len(page) - len(existing)
            run.events_existing += len(existing)
            last = page[-1]
            cursor_received, cursor_event = last.received_utc, last.event_id
            if state.high_water_received_utc is None or last.received_utc > state.high_water_received_utc:
                state.high_water_received_utc = last.received_utc
            run.high_water_received_utc = state.high_water_received_utc
            self.db.commit()  # per-page commit: progress is durable, nothing is ever deleted
            if len(page) < settings.sync_page_size:
                break

    def _snapshot_agent_status(self, source) -> None:
        now = datetime.now(UTC)
        for a in source.list_agent_status():
            row = self.db.get(AgentStatus, a.site_id) or AgentStatus(site_id=a.site_id)
            for field in ("agent_instance_id", "agent_version", "health", "health_reason", "source_epoch",
                          "high_water_id", "source_connected", "last_source_poll_utc", "last_delivery_utc",
                          "pending_count", "dead_letter_count", "oldest_pending_age_seconds", "last_error",
                          "last_heartbeat_utc", "heartbeat_count"):
                setattr(row, field, getattr(a, field))
            row.snapshot_at = now
            self.db.add(row)
        self.db.commit()

    def _reconcile(self, source) -> list[dict]:
        mirror = {
            (s, ep): (c, m) for s, ep, c, m in self.db.execute(
                select(
                    AttendanceEvent.site_id, AttendanceEvent.source_epoch,
                    func.count(), func.max(AttendanceEvent.received_utc),
                )
                .group_by(AttendanceEvent.site_id, AttendanceEvent.source_epoch)
            ).all()
        }
        out = []
        keys = set(mirror)
        for t in source.epoch_totals():
            keys.discard((t.site_id, t.source_epoch))
            m_count, m_max = mirror.get((t.site_id, t.source_epoch), (0, None))
            out.append({
                "site_id": t.site_id, "source_epoch": t.source_epoch,
                "source_count": t.event_count, "mirror_count": int(m_count),
                "source_max_received_utc": t.max_received_utc, "mirror_max_received_utc": m_max,
                "in_sync": int(m_count) == t.event_count and m_max == t.max_received_utc,
            })
        for s, ep in sorted(keys):  # mirrored rows the source no longer reports — flagged, never deleted
            m_count, m_max = mirror[(s, ep)]
            out.append({"site_id": s, "source_epoch": ep, "source_count": 0, "mirror_count": int(m_count),
                        "source_max_received_utc": None, "mirror_max_received_utc": m_max, "in_sync": False})
        return sorted(out, key=lambda r: (r["site_id"], r["source_epoch"]))


def _safe_error(exc: Exception) -> str:
    msg = str(exc).splitlines()[0][:200] if str(exc) else exc.__class__.__name__
    return f"{exc.__class__.__name__}: {msg}"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def run_dto(run: OnsiteSyncRun) -> dict:
    return {
        "run_id": run.run_id, "status": run.status, "trigger_type": run.trigger_type,
        "requested_at": _iso(run.requested_at), "started_at": _iso(run.started_at), "completed_at": _iso(run.completed_at),
        "events_read": run.events_read, "events_inserted": run.events_inserted, "events_existing": run.events_existing,
        "sites_discovered": run.sites_discovered,
        "high_water_received_utc": _iso(run.high_water_received_utc), "source_unavailable": run.source_unavailable,
        "error_summary": run.error_summary,
    }
