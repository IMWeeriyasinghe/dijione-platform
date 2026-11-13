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

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models.mirror import AgentStatus, AttendanceEvent


class AttendanceRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _emp_filter(emp_codes: Collection[str] | None) -> list:
        return [] if emp_codes is None else [AttendanceEvent.emp_code.in_(list(emp_codes) or [""])]

    @staticmethod
    def _windows(code_windows: Collection[tuple[str, date, date]] | None) -> list:
        """Verified-identity filter: only events of ``code`` on site-local days
        ``lo..hi`` (inclusive) of each window. ``None`` = no filter; an empty
        collection matches nothing (fail closed)."""
        if code_windows is None:
            return []
        clauses = [and_(AttendanceEvent.emp_code == c, AttendanceEvent.site_local_date >= lo,
                        AttendanceEvent.site_local_date <= hi) for c, lo, hi in code_windows]
        return [or_(*clauses)] if clauses else [AttendanceEvent.event_id.is_(None)]

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
        self, *, allowed_site_ids: Collection[str], site_id: str, local_date: date, date_to: date | None = None
    ) -> list[tuple[str, int, int]]:
        """(local hour "HH", events, distinct employees) for one site-local day
        or an inclusive site-local date range (summed per hour of day).
        The hour comes from the source's own local wall clock
        (punch_time_local "YYYY-MM-DDTHH:..."), never from UTC."""
        if site_id not in allowed_site_ids:
            return []
        hour = func.substr(AttendanceEvent.punch_time_local, 12, 2)
        return [tuple(r) for r in self.db.execute(
            select(hour, func.count(), func.count(func.distinct(AttendanceEvent.emp_code)))
            .where(*self._range(site_id, local_date, date_to or local_date))
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
        utc_windows: Collection[tuple[datetime, datetime]] | None = None, oldest_first: bool = False,
        code_windows: Collection[tuple[str, date, date]] | None = None,
    ) -> tuple[int, list[AttendanceEvent]]:
        """Newest-first (or oldest-first) raw events plus the total count.
        ``utc_windows`` keeps only events with ``start <= punch_time_utc < end``
        in any window (exact hour drill-down, no double counting at the edges).
        Ordering is total and stable: (punch_time_utc, event_id)."""
        if site_id not in allowed_site_ids:
            return 0, []
        where = [*self._range(site_id, date_from, date_to), *self._emp_filter(emp_codes),
                 *self._windows(code_windows)]
        if terminal:
            where.append(AttendanceEvent.terminal_alias == terminal)
        if tz_inconsistent_only:
            where.append(AttendanceEvent.tz_consistent.is_(False))
        if utc_windows is not None:
            if not utc_windows:
                return 0, []
            where.append(or_(*[and_(AttendanceEvent.punch_time_utc >= s, AttendanceEvent.punch_time_utc < e)
                               for s, e in utc_windows]))
        order = (AttendanceEvent.punch_time_utc.asc(), AttendanceEvent.event_id.asc()) if oldest_first else \
            (AttendanceEvent.punch_time_utc.desc(), AttendanceEvent.event_id.desc())
        total = int(self.db.execute(select(func.count()).select_from(AttendanceEvent).where(*where)).scalar_one())
        rows = list(self.db.execute(
            select(AttendanceEvent).where(*where)
            .order_by(*order)
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

    def punch_rows(
        self, *, allowed_site_ids: Collection[str], site_id: str, date_from: date, date_to: date,
        emp_codes: Collection[str] | None = None,
    ) -> list[tuple[date, str, datetime, str | None]]:
        """(local_date, emp_code, punch_time_utc, terminal_sn) ordered by time —
        used to merge several ZKBioTime IDs of one employee into one day."""
        if site_id not in allowed_site_ids:
            return []
        return [tuple(r) for r in self.db.execute(
            select(AttendanceEvent.site_local_date, AttendanceEvent.emp_code, AttendanceEvent.punch_time_utc,
                   AttendanceEvent.terminal_sn)
            .where(*self._range(site_id, date_from, date_to), *self._emp_filter(emp_codes))
            .order_by(AttendanceEvent.site_local_date, AttendanceEvent.punch_time_utc, AttendanceEvent.event_id)
        ).all()]

    def code_day_stats(
        self, *, allowed_site_ids: Collection[str], site_id: str, date_from: date | None = None,
        date_to: date | None = None, code_windows: Collection[tuple[str, date, date]] | None = None,
    ) -> list[tuple[str, date, int, datetime]]:
        """(emp_code, local_date, events, last_punch_utc) per code-day, optionally
        restricted to verified-identity windows and/or a date range."""
        if site_id not in allowed_site_ids:
            return []
        where = [AttendanceEvent.site_id == site_id, *self._windows(code_windows)]
        if date_from is not None:
            where.append(AttendanceEvent.site_local_date >= date_from)
        if date_to is not None:
            where.append(AttendanceEvent.site_local_date <= date_to)
        return [tuple(r) for r in self.db.execute(
            select(AttendanceEvent.emp_code, AttendanceEvent.site_local_date, func.count(),
                   func.max(AttendanceEvent.punch_time_utc))
            .where(*where).group_by(AttendanceEvent.emp_code, AttendanceEvent.site_local_date)
        ).all()]

    def code_day_hours(
        self, *, allowed_site_ids: Collection[str], site_id: str, date_from: date, date_to: date,
        code_windows: Collection[tuple[str, date, date]] | None = None,
    ) -> list[tuple[str, str, date, int]]:
        """(local hour "HH", emp_code, local_date, events) — hourly counts that
        can be resolved to distinct verified employees."""
        if site_id not in allowed_site_ids:
            return []
        hour = func.substr(AttendanceEvent.punch_time_local, 12, 2)
        return [tuple(r) for r in self.db.execute(
            select(hour, AttendanceEvent.emp_code, AttendanceEvent.site_local_date, func.count())
            .where(*self._range(site_id, date_from, date_to), *self._windows(code_windows))
            .group_by(hour, AttendanceEvent.emp_code, AttendanceEvent.site_local_date)
        ).all()]

    def date_bounds(self, *, allowed_site_ids: Collection[str], site_id: str) -> tuple[date | None, date | None]:
        if site_id not in allowed_site_ids:
            return None, None
        row = self.db.execute(
            select(func.min(AttendanceEvent.site_local_date), func.max(AttendanceEvent.site_local_date))
            .where(AttendanceEvent.site_id == site_id)
        ).one()
        return row[0], row[1]
