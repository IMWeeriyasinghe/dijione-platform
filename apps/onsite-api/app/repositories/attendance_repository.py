"""Site-scoped reads of the attendance mirror.

Every public read method REQUIRES ``allowed_site_ids`` (keyword-only, no
default) — the fail-closed site allow-list resolved from the caller's
On-site scope. ``tests/test_site_scope_guard.py`` enforces this.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date, datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.mirror import AgentStatus, AttendanceEvent


class AttendanceRepository:
    def __init__(self, db: Session):
        self.db = db

    def event_count(self, *, allowed_site_ids: Collection[str]) -> int:
        if not allowed_site_ids:
            return 0
        return int(self.db.execute(
            select(func.count()).select_from(AttendanceEvent).where(AttendanceEvent.site_id.in_(allowed_site_ids))
        ).scalar_one())

    def latest_by_site(self, *, allowed_site_ids: Collection[str]) -> dict[str, dict]:
        """Per site: latest received (UTC) and latest punch (UTC)."""
        if not allowed_site_ids:
            return {}
        rows = self.db.execute(
            select(AttendanceEvent.site_id, func.max(AttendanceEvent.received_utc), func.max(AttendanceEvent.punch_time_utc))
            .where(AttendanceEvent.site_id.in_(allowed_site_ids))
            .group_by(AttendanceEvent.site_id)
        ).all()
        return {s: {"latest_received_utc": r, "latest_punch_utc": p} for s, r, p in rows}

    def emp_code_activity(self, *, allowed_site_ids: Collection[str]) -> list[tuple[str, int, date, date]]:
        """(emp_code, event_count, first_local_date, last_local_date) across allowed sites."""
        if not allowed_site_ids:
            return []
        return [tuple(r) for r in self.db.execute(
            select(AttendanceEvent.emp_code, func.count(), func.min(AttendanceEvent.site_local_date),
                   func.max(AttendanceEvent.site_local_date))
            .where(AttendanceEvent.site_id.in_(allowed_site_ids))
            .group_by(AttendanceEvent.emp_code)
            .order_by(AttendanceEvent.emp_code)
        ).all()]

    def daily_groups(
        self, *, allowed_site_ids: Collection[str], site_id: str, date_from: date, date_to: date
    ) -> list[tuple[str, date, str, int, datetime, datetime, int, int]]:
        """``GROUP BY site_id, site_local_date, emp_code`` computed on read:
        (site_id, local_date, emp_code, punch_count, first_utc, last_utc,
        distinct_terminals, tz_inconsistent_count)."""
        if site_id not in allowed_site_ids:
            return []
        inconsistent = func.sum(case((AttendanceEvent.tz_consistent.is_(False), 1), else_=0))
        return [tuple(r) for r in self.db.execute(
            select(
                AttendanceEvent.site_id, AttendanceEvent.site_local_date, AttendanceEvent.emp_code,
                func.count(), func.min(AttendanceEvent.punch_time_utc), func.max(AttendanceEvent.punch_time_utc),
                func.count(func.distinct(AttendanceEvent.terminal_sn)), inconsistent,
            )
            .where(
                AttendanceEvent.site_id == site_id,
                AttendanceEvent.site_local_date >= date_from,
                AttendanceEvent.site_local_date <= date_to,
            )
            .group_by(AttendanceEvent.site_id, AttendanceEvent.site_local_date, AttendanceEvent.emp_code)
            .order_by(AttendanceEvent.site_local_date, AttendanceEvent.emp_code)
        ).all()]

    def punch_times(
        self, *, allowed_site_ids: Collection[str], site_id: str, date_from: date, date_to: date
    ) -> list[tuple[date, str, datetime]]:
        """(local_date, emp_code, punch_time_utc) ordered — for duplicate-tap detection."""
        if site_id not in allowed_site_ids:
            return []
        return [tuple(r) for r in self.db.execute(
            select(AttendanceEvent.site_local_date, AttendanceEvent.emp_code, AttendanceEvent.punch_time_utc)
            .where(
                AttendanceEvent.site_id == site_id,
                AttendanceEvent.site_local_date >= date_from,
                AttendanceEvent.site_local_date <= date_to,
            )
            .order_by(AttendanceEvent.site_local_date, AttendanceEvent.emp_code, AttendanceEvent.punch_time_utc)
        ).all()]

    def agent_status(self, *, allowed_site_ids: Collection[str]) -> list[AgentStatus]:
        if not allowed_site_ids:
            return []
        return list(self.db.execute(
            select(AgentStatus).where(AgentStatus.site_id.in_(allowed_site_ids)).order_by(AgentStatus.site_id)
        ).scalars())
