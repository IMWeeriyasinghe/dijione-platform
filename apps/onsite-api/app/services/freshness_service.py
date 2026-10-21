"""Freshness distinguishes "no attendance recorded" from "feed may be stale"
— a pipeline outage must never be presented as employee absence."""

from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import FeedState
from app.repositories.attendance_repository import AttendanceRepository
from app.services.mirror_sync_service import MirrorSyncService, run_dto


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def freshness(db: Session, *, allowed_site_ids: Collection[str], technical: bool = False,
              now: datetime | None = None) -> dict:
    settings = get_settings()
    now = now or datetime.now(UTC)
    svc = MirrorSyncService(db)
    latest, success = svc.latest(), svc.last_successful()
    last_success_at = _aware(success.completed_at) if success else None
    repo = AttendanceRepository(db)
    latest_by_site = repo.latest_by_site(allowed_site_ids=allowed_site_ids)
    agents = {a.site_id: a for a in repo.agent_status(allowed_site_ids=allowed_site_ids)}

    sites = []
    for site_id in sorted(allowed_site_ids):
        agent = agents.get(site_id)
        heartbeat = _aware(agent.last_heartbeat_utc) if agent else None
        if latest is not None and latest.status == "FAILED" and latest.source_unavailable:
            state = FeedState.SOURCE_UNAVAILABLE
        elif last_success_at is None:
            state = FeedState.NOT_SYNCED
        elif heartbeat is None or now - heartbeat > timedelta(minutes=settings.heartbeat_stale_minutes):
            state = FeedState.STALE
        elif (agent and agent.pending_count > 0) or now - last_success_at > timedelta(minutes=2 * settings.sync_cadence_minutes):
            state = FeedState.DELAYED
        else:
            state = FeedState.FRESH
        info = latest_by_site.get(site_id, {})
        site = {
            "site_id": site_id, "feed_state": state.value,
            "latest_received_utc": _iso(_aware(info.get("latest_received_utc"))),
            "latest_punch_utc": _iso(_aware(info.get("latest_punch_utc"))),
            "agent_heartbeat_utc": _iso(heartbeat),
            "agent_health": agent.health if agent else None,
        }
        if technical and agent:
            site["agent"] = {
                "agent_version": agent.agent_version, "health_reason": agent.health_reason,
                "source_epoch": agent.source_epoch, "high_water_id": agent.high_water_id,
                "source_connected": agent.source_connected, "pending_count": agent.pending_count,
                "dead_letter_count": agent.dead_letter_count,
                "oldest_pending_age_seconds": agent.oldest_pending_age_seconds,
                "last_error": agent.last_error, "last_delivery_utc": _iso(_aware(agent.last_delivery_utc)),
            }
        sites.append(site)

    return {
        "last_successful_sync_at": _iso(last_success_at),
        "latest_run": run_dto(latest) if latest else None,
        "sites": sites,
    }
