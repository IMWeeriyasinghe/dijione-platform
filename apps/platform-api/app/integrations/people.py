"""Employee-record check against BambooHR, through the People / Workforce domain (people-api).

DijiOne does not integrate BambooHR a second time: it reads people-api's internal contract with
the existing shared clients. Only three facts are kept, in memory, for a few minutes: the work
email, the Employee Number and the employment status. Nothing here writes anywhere.

A person is MATCHED when either
  * their work email equals an Active employee's work email, or
  * the directory's employeeId is set and equals the Employee Number of exactly one Active
    workforce-directory entry.
NOT_FOUND when people-api answered and neither applies; UNKNOWN when people-api could not be read.
An UNKNOWN answer never grants anything and never overwrites a stored result.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)

MATCHED, NOT_FOUND, UNKNOWN = "MATCHED", "NOT_FOUND", "UNKNOWN"
_TTL_SECONDS = 300


@dataclass(frozen=True)
class EmployeeRecord:
    status: str  # MATCHED / NOT_FOUND / UNKNOWN
    employee_number: str | None = None
    employment_status: str | None = None


@dataclass(frozen=True)
class _Snapshot:
    by_email: dict[str, tuple[str | None, str]]  # email -> (employee number, employment status)
    by_number: dict[str, list[str]]  # employee number -> employment statuses (Active entries only)


class PeopleSource(Protocol):
    def active_employees(self) -> list[dict]: ...
    def active_workforce(self) -> list[dict]: ...


class PeopleApiSource:
    """people-api over internal ingress (X-Internal-Token), using the shared clients."""

    def __init__(self, *, timeout: float = 10.0) -> None:
        self._timeout = timeout

    def _clients(self):
        from auth_client_py.people_client import EmployeeDirectoryClient
        from auth_client_py.workforce_client import WorkforceDirectoryClient

        settings = get_settings()
        if not settings.people_api_url:
            raise RuntimeError("PEOPLE_API_URL is not configured")
        kwargs = dict(timeout=self._timeout, caller="platform-api")
        return (
            EmployeeDirectoryClient(settings.people_api_url, settings.internal_service_secret, **kwargs),
            WorkforceDirectoryClient(settings.people_api_url, settings.internal_service_secret, **kwargs),
        )

    def active_employees(self) -> list[dict]:
        return self._clients()[0].list_employees(active_only=True)

    def active_workforce(self) -> list[dict]:
        return self._clients()[1].list_entries(status="active")


class EmployeeRecordChecker:
    def __init__(self, source: PeopleSource | None = None) -> None:
        self._source = source or PeopleApiSource()
        self._snapshot: _Snapshot | None = None
        self._loaded_at = 0.0
        self._lock = threading.Lock()

    def _load(self) -> _Snapshot | None:
        with self._lock:
            if self._snapshot is not None and time.monotonic() - self._loaded_at < _TTL_SECONDS:
                return self._snapshot
            employees = workforce = None
            for attempt in (1, 2):  # one retry: a transient transport failure (seen on a fresh replica)
                try:
                    employees = self._source.active_employees()
                    workforce = self._source.active_workforce()
                    break
                except Exception as exc:  # people-api down, misconfigured, or answered an error
                    logger.warning("Employee records unavailable (attempt %d): %s", attempt, type(exc).__name__)
            if employees is None or workforce is None:
                return None
            by_email = {
                (e.get("work_email") or "").strip().lower(): (e.get("employee_number"), e.get("employment_status") or "")
                for e in employees
                if (e.get("work_email") or "").strip()
            }
            by_number: dict[str, list[str]] = {}
            for w in workforce:
                number = (w.get("employee_number") or "").strip()
                if number and (w.get("employment_status") or "").lower() == "active":
                    by_number.setdefault(number, []).append(w.get("employment_status") or "Active")
            self._snapshot, self._loaded_at = _Snapshot(by_email=by_email, by_number=by_number), time.monotonic()
            return self._snapshot

    def cached(self) -> _Snapshot | None:
        """The current snapshot if one is loaded and fresh; never calls people-api and never waits
        for a load in progress (no lock: a sign-in must not queue behind the HR source)."""
        snapshot, loaded_at = self._snapshot, self._loaded_at
        if snapshot is not None and time.monotonic() - loaded_at < _TTL_SECONDS:
            return snapshot
        return None

    def warm_in_background(self) -> None:
        threading.Thread(target=self._load, name="employee-records-warm", daemon=True).start()

    def check(
        self, *, email: str | None, employee_id: str | None = None, cached_only: bool = False,
        wait_seconds: float = 0.0,
    ) -> EmployeeRecord:
        """``cached_only`` (sign-in) answers from an already-loaded snapshot, or UNKNOWN while one is
        loaded in the background. ``wait_seconds`` (first sign-in only) waits, strictly bounded, for
        that one background load to finish; it never starts more than one load or calls people-api
        itself."""
        if cached_only:
            snapshot = self.cached()
            if snapshot is None:
                self.warm_in_background()
                deadline = time.monotonic() + min(max(wait_seconds, 0.0), 5.0)
                while snapshot is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                    snapshot = self.cached()
        else:
            snapshot = self._load()
        if snapshot is None:
            return EmployeeRecord(UNKNOWN)
        hit = snapshot.by_email.get((email or "").strip().lower())
        if hit is not None:
            return EmployeeRecord(MATCHED, employee_number=hit[0], employment_status=hit[1] or None)
        number = (employee_id or "").strip()
        if number and len(snapshot.by_number.get(number, [])) == 1:
            return EmployeeRecord(MATCHED, employee_number=number, employment_status=snapshot.by_number[number][0])
        return EmployeeRecord(NOT_FOUND)

    def invalidate(self) -> None:
        with self._lock:
            self._snapshot = None


_checker: EmployeeRecordChecker | None = None
_checker_lock = threading.Lock()


def get_employee_record_checker() -> EmployeeRecordChecker:
    global _checker
    with _checker_lock:
        if _checker is None:
            _checker = EmployeeRecordChecker()
        return _checker


def set_employee_record_checker(checker: EmployeeRecordChecker | None) -> None:
    global _checker
    with _checker_lock:
        _checker = checker
