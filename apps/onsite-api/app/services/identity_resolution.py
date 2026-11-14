"""Verified identity resolution: ZKBioTime ID + site-local day -> BambooHR employee.

The ONLY attribution path in Diji On-site. A code-day is attributed to an
employee exactly when one administrator-verified mapping of that code at that
site covers the day (inclusive ``valid_from``..``valid_to``). Everything else
is UNMAPPED (or MAPPING_CONFLICT, defensively) and must not appear in
viewer-facing records. BambooHR Employee Number equality is never consulted.

Loaded once per request: one indexed SELECT of the (small) mapping table,
then in-memory interval lookups.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.core.constants import IDENTIFIED_STATUSES, IdentityClass, MappingStatus
from app.repositories.identity_repository import IdentityRepository
from app.services.workforce_directory import DirectorySnapshot


@dataclass(frozen=True)
class MappingPeriod:
    """Detached snapshot of one VERIFIED mapping row."""

    id: int
    site_id: str
    zk_emp_code: str
    bamboohr_id: str
    valid_from: date
    valid_to: date | None
    employee_number_snapshot: str | None = None
    display_name_snapshot: str | None = None

    def covers(self, day: date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day <= self.valid_to)

    def clip(self, start: date, end: date) -> tuple[date, date] | None:
        lo = max(start, self.valid_from)
        hi = min(end, self.valid_to) if self.valid_to is not None else end
        return (lo, hi) if lo <= hi else None


@dataclass(frozen=True)
class ResolvedIdentity:
    emp_code: str
    mapping_status: MappingStatus
    mapping_id: int | None = None
    bamboohr_id: str | None = None
    employee_number: str | None = None
    employee_name: str | None = None
    department: str | None = None
    job_title: str | None = None
    employment_status: str | None = None
    has_photo: bool = False
    mapping_valid_from: date | None = None
    mapping_valid_to: date | None = None
    entry: dict | None = field(default=None, compare=False, repr=False)

    @property
    def identified(self) -> bool:
        return self.mapping_status in IDENTIFIED_STATUSES


def _parse(d: str | None) -> date | None:
    return date.fromisoformat(d) if d else None


def legacy_identity_class(resolved: ResolvedIdentity, first: date, last: date) -> str | None:
    """LEGACY label for the backward-compatible contract, derived only from the
    verified mapping's employee. ``None`` when the directory is unavailable
    (the pre-redesign behaviour); never UNMATCHED/AMBIGUOUS — unidentified
    code-days are not emitted at all."""
    st = resolved.mapping_status
    if st == MappingStatus.DIRECTORY_UNAVAILABLE or not resolved.identified:
        return None
    if st == MappingStatus.MAPPED_DIRECTORY_MISSING or resolved.entry is None:
        return IdentityClass.MATCHED_INACTIVE.value
    e = resolved.entry
    term = _parse(e.get("termination_date"))
    if e.get("employment_status") != "Active" or (term is not None and last > term):
        return IdentityClass.MATCHED_INACTIVE.value
    hire = _parse(e.get("hire_date"))
    if hire is not None and first < hire:
        return IdentityClass.MATCHED_BEFORE_HIRE.value
    return IdentityClass.MATCHED_ACTIVE.value


class MappingIndex:
    def __init__(self, periods: Iterable[MappingPeriod], directory: DirectorySnapshot):
        self.directory = directory
        self.available = directory.available
        self._people = directory.by_bamboohr_id() if directory.available else {}
        self._by_code: dict[tuple[str, str], list[MappingPeriod]] = defaultdict(list)
        self._by_employee: dict[str, list[MappingPeriod]] = defaultdict(list)
        for p in periods:
            self._by_code[(p.site_id, p.zk_emp_code)].append(p)
            self._by_employee[p.bamboohr_id].append(p)
        self._starts: dict[tuple[str, str], list[date]] = {}
        for key, ps in self._by_code.items():
            ps.sort(key=lambda p: (p.valid_from, p.id))
            self._starts[key] = [p.valid_from for p in ps]

    @classmethod
    def load(cls, db: Session, *, allowed_site_ids: Collection[str], directory: DirectorySnapshot) -> MappingIndex:
        rows = IdentityRepository(db).verified_mappings(allowed_site_ids=allowed_site_ids)
        return cls([MappingPeriod(r.id, r.site_id, r.zk_emp_code, r.bamboohr_id, r.valid_from, r.valid_to,
                                  r.employee_number_snapshot, r.display_name_snapshot) for r in rows], directory)

    # --- lookups -------------------------------------------------------------

    def periods_covering(self, site_id: str, code: str, day: date) -> list[MappingPeriod]:
        ps = self._by_code.get((site_id, code))
        if not ps:
            return []
        i = bisect.bisect_right(self._starts[(site_id, code)], day)
        # Periods never overlap after validation, but be defensive: scan all
        # candidates that start on/before the day.
        return [p for p in ps[:i] if p.covers(day)]

    def resolve(self, site_id: str, code: str, day: date) -> ResolvedIdentity:
        covering = self.periods_covering(site_id, code, day)
        if not covering:
            return ResolvedIdentity(emp_code=code, mapping_status=MappingStatus.UNMAPPED)
        if len({p.bamboohr_id for p in covering}) > 1 or len(covering) > 1:
            return ResolvedIdentity(emp_code=code, mapping_status=MappingStatus.MAPPING_CONFLICT)
        return self._describe(code, covering[0])

    def _describe(self, code: str, p: MappingPeriod) -> ResolvedIdentity:
        base = dict(emp_code=code, mapping_id=p.id, bamboohr_id=p.bamboohr_id,
                    mapping_valid_from=p.valid_from, mapping_valid_to=p.valid_to)
        if not self.available:
            return ResolvedIdentity(mapping_status=MappingStatus.DIRECTORY_UNAVAILABLE,
                                    employee_number=p.employee_number_snapshot,
                                    employee_name=p.display_name_snapshot, **base)
        e = self._people.get(p.bamboohr_id)
        if e is None:
            return ResolvedIdentity(mapping_status=MappingStatus.MAPPED_DIRECTORY_MISSING,
                                    employee_number=p.employee_number_snapshot,
                                    employee_name=p.display_name_snapshot, **base)
        return ResolvedIdentity(
            mapping_status=MappingStatus.MAPPED, employee_number=e.get("employee_number"),
            employee_name=e.get("display_name"), department=e.get("department"), job_title=e.get("job_title"),
            employment_status=e.get("employment_status"), has_photo=bool(e.get("has_photo")), entry=e, **base)

    def employee(self, bamboohr_id: str) -> dict | None:
        return self._people.get(bamboohr_id)

    def describe_employee(self, bamboohr_id: str, site_id: str | None = None) -> ResolvedIdentity | None:
        """Profile of a verified employee (most recent mapping at the site)."""
        ps = [p for p in self._by_employee.get(bamboohr_id, []) if site_id is None or p.site_id == site_id]
        if not ps:
            return None
        latest = max(ps, key=lambda p: (p.valid_to or date.max, p.valid_from))
        return self._describe(latest.zk_emp_code, latest)

    def windows(self, site_id: str, start: date, end: date, *, codes: Collection[str] | None = None,
                bamboohr_ids: Collection[str] | None = None) -> list[tuple[str, date, date]]:
        """``(code, lo, hi)`` verified windows clipped to ``start..end``. An empty
        list means "nothing is attributable" — callers must fail closed."""
        out = []
        for (site, code), ps in self._by_code.items():
            if site != site_id or (codes is not None and code not in codes):
                continue
            for p in ps:
                if bamboohr_ids is not None and p.bamboohr_id not in bamboohr_ids:
                    continue
                clipped = p.clip(start, end)
                if clipped:
                    out.append((code, *clipped))
        return out

    def employees_in_period(self, site_id: str, start: date, end: date) -> dict[str, list[MappingPeriod]]:
        out: dict[str, list[MappingPeriod]] = defaultdict(list)
        for (site, _code), ps in self._by_code.items():
            if site != site_id:
                continue
            for p in ps:
                if p.clip(start, end):
                    out[p.bamboohr_id].append(p)
        return dict(out)

    def periods_for_code(self, site_id: str, code: str) -> list[MappingPeriod]:
        return list(self._by_code.get((site_id, code), []))

    def periods_for_employee(self, bamboohr_id: str, site_id: str | None = None) -> list[MappingPeriod]:
        return [p for p in self._by_employee.get(bamboohr_id, []) if site_id is None or p.site_id == site_id]

    def any_mapping_for_code(self, code: str) -> bool:
        return any(c == code for _s, c in self._by_code)
