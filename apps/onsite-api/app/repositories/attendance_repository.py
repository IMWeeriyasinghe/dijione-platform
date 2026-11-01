"""Site-scoped reads of the attendance mirror.

Every public read method REQUIRES ``allowed_site_ids`` (keyword-only, no
default) — the fail-closed site allow-list resolved from the caller's
On-site scope. ``tests/test_module_boundaries.py`` enforces this.

All Dashboard V1 aggregation happens here, in SQL — the browser never
receives tens of thousands of raw rows to aggregate client-side.
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

    @staticmethod
    def _emp_filter(emp_codes: Collection[str] | None) -> list:
        return [] if emp_codes is None else [AttendanceEvent.emp_code.in_(list(emp_codes) or [""])]

    @staticmethod
    def _range(site_id: str, date_from: date, date_to: date) -> list:
        return [
            AttendanceEvent.site_id == site_id,
            AttendanceEvent.site_local_date >= date_from,
            AttendanceEvent.site_local_date <= date_to,
        ]

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
        self, *, allowed_site_ids: Collection[str], site_id: str, date_from: date, date_to: date,
        emp_codes: Collection[str] | None = None,
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
            .where(*self._range(site_id, date_from, date_to), *self._emp_filter(emp_codes))
            .group_by(AttendanceEvent.site_id, AttendanceEvent.site_local_date, AttendanceEvent.emp_code)
            .order_by(AttendanceEvent.site_local_date, AttendanceEvent.emp_code)
        ).all()]

    def punch_times(
        self, *, allowed_site_ids: Collection[str], site_id: str, date_from: date, date_to: date,
        emp_codes: Collection[str] | None = None,
    ) -> list[tuple[date, str, datetime]]:
        """(local_date, emp_code, punch_time_utc) ordered — for duplicate-tap detection."""
        if site_id not in allowed_site_ids:
            return []
        return [tuple(r) for r in self.db.execute(
            select(AttendanceEvent.site_local_date, AttendanceEvent.emp_code, AttendanceEvent.punch_time_utc)
            .where(*self._range(site_id, date_from, date_to), *self._emp_filter(emp_codes))
            .order_by(AttendanceEvent.site_local_date, AttendanceEvent.emp_code, AttendanceEvent.punch_time_utc)
        ).all()]

    def agent_status(self, *, allowed_site_ids: Collection[str]) -> list[AgentStatus]:
        if not allowed_site_ids:
            return []
        return list(self.db.execute(
            select(AgentStatus).where(AgentStatus.site_id.in_(allowed_site_ids)).order_by(AgentStatus.site_id)
        ).scalars())

    # --- Dashboard V1 aggregates -------------------------------------------

    def hourly_counts(
        self, *, allowed_site_ids: Collection[str], site_id: str, local_date: date
    ) -> list[tuple[str, int, int]]:
        """(local hour "HH", events, distinct employees) for one site-local day.
        The hour comes from the source's own local wall clock
        (punch_time_local "YYYY-MM-DDTHH:..."), never from UTC."""
        if site_id not in allowed_site_ids:
            return []
        hour = func.substr(AttendanceEvent.punch_time_local, 12, 2)
        return [tuple(r) for r in self.db.execute(
            select(hour, func.count(), func.count(func.distinct(AttendanceEvent.emp_code)))
            .where(*self._range(site_id, local_date, local_date))
            .group_by(hour).order_by(hour)
        ).all()]

    def daily_trend(
        self, *, allowed_site_ids: Collection[str], site_id: str, date_from: date, date_to: date
    ) -> list[tuple[date, int, int]]:
        """(local_date, events, distinct employees) per day."""
        if site_id not in allowed_site_ids:
            return []
        return [tuple(r) for r in self.db.execute(
            select(AttendanceEvent.site_local_date, func.count(), func.count(func.distinct(AttendanceEvent.emp_code)))
            .where(*self._range(site_id, date_from, date_to))
            .group_by(AttendanceEvent.site_local_date).order_by(AttendanceEvent.site_local_date)
        ).all()]

    def events_page(
        self, *, allowed_site_ids: Collection[str], site_id: str, date_from: date, date_to: date,
        emp_codes: Collection[str] | None = None, terminal: str | None = None,
        tz_inconsistent_only: bool = False, offset: int = 0, limit: int = 50,
    ) -> tuple[int, list[AttendanceEvent]]:
        """Newest-first raw events (verbatim mirror rows) plus the total count."""
        if site_id not in allowed_site_ids:
            return 0, []
        where = [*self._range(site_id, date_from, date_to), *self._emp_filter(emp_codes)]
        if terminal:
            where.append(AttendanceEvent.terminal_alias == terminal)
        if tz_inconsistent_only:
            where.append(AttendanceEvent.tz_consistent.is_(False))
        total = int(self.db.execute(select(func.count()).select_from(AttendanceEvent).where(*where)).scalar_one())
        rows = list(self.db.execute(
            select(AttendanceEvent).where(*where)
            .order_by(AttendanceEvent.punch_time_utc.desc(), AttendanceEvent.event_id.desc())
            .offset(offset).limit(limit)
        ).scalars())
        return total, rows

    def terminals_by_day(
        self, *, allowed_site_ids: Collection[str], site_id: str, date_from: date, date_to: date,
        emp_codes: Collection[str] | None = None,
    ) -> list[tuple[date, str, str | None]]:
        """Distinct (local_date, emp_code, terminal_alias)."""
        if site_id not in allowed_site_ids:
            return []
        return [tuple(r) for r in self.db.execute(
            select(AttendanceEvent.site_local_date, AttendanceEvent.emp_code, AttendanceEvent.terminal_alias)
            .where(*self._range(site_id, date_from, date_to), *self._emp_filter(emp_codes))
            .distinct()
        ).all()]

    def terminal_names(self, *, allowed_site_ids: Collection[str], site_id: str) -> list[str]:
        if site_id not in allowed_site_ids:
            return []
        return [t for t in self.db.execute(
            select(AttendanceEvent.terminal_alias).where(AttendanceEvent.site_id == site_id)
            .distinct().order_by(AttendanceEvent.terminal_alias)
        ).scalars() if t]

    def distinct_codes(
        self, *, allowed_site_ids: Collection[str], site_id: str, date_from: date, date_to: date
    ) -> list[str]:
        if site_id not in allowed_site_ids:
            return []
        return list(self.db.execute(
            select(AttendanceEvent.emp_code).where(*self._range(site_id, date_from, date_to)).distinct()
        ).scalars())

    def employee_activity(
        self, *, allowed_site_ids: Collection[str], site_id: str, date_from: date, date_to: date
    ) -> list[tuple[str, int, int, datetime]]:
        """(emp_code, events, activity_days, last_punch_utc) within the range."""
        if site_id not in allowed_site_ids:
            return []
        return [tuple(r) for r in self.db.execute(
            select(AttendanceEvent.emp_code, func.count(), func.count(func.distinct(AttendanceEvent.site_local_date)),
                   func.max(AttendanceEvent.punch_time_utc))
            .where(*self._range(site_id, date_from, date_to))
            .group_by(AttendanceEvent.emp_code)
        ).all()]

    def last_activity(self, *, allowed_site_ids: Collection[str], site_id: str) -> dict[str, datetime]:
        """Latest punch (UTC) per emp_code across all mirrored history for a site."""
        if site_id not in allowed_site_ids:
            return {}
        return dict(self.db.execute(
            select(AttendanceEvent.emp_code, func.max(AttendanceEvent.punch_time_utc))
            .where(AttendanceEvent.site_id == site_id).group_by(AttendanceEvent.emp_code)
        ).all())

    def date_bounds(self, *, allowed_site_ids: Collection[str], site_id: str) -> tuple[date | None, date | None]:
        if site_id not in allowed_site_ids:
            return None, None
        row = self.db.execute(
            select(func.min(AttendanceEvent.site_local_date), func.max(AttendanceEvent.site_local_date))
            .where(AttendanceEvent.site_id == site_id)
        ).one()
        return row[0], row[1]
