"""EmployeeSourceClient interface. birthday-api consumes People / Workforce
data over this interface — never BambooHR directly (Architecture Completion
Plan §3). The real implementation (``http_adapter.py``) calls people-api;
the mock (``mock_adapter.py``) is realistic in-memory fixture data.
"""

from abc import ABC, abstractmethod

from app.integrations.people_source.schemas import EmployeeRecord


class EmployeeSourceClient(ABC):
    @abstractmethod
    def list_active_employees(self) -> list[EmployeeRecord]: ...

    @abstractmethod
    def get_employee(self, employee_id: str) -> EmployeeRecord | None:
        """Single-employee lookup by the stable provider id — used by the
        employee_number backfill script, not by the daily scan."""
        ...


class EmployeeSourceFetchError(Exception):
    """Raised when an employee-directory fetch fails. Callers must catch
    this and record an audit event (no PII) rather than letting employee
    data leak into an error message."""


class EmployeeSourceUnavailableError(EmployeeSourceFetchError):
    """The People / Workforce source domain (people-api) could not be
    reached at all (connection/timeout) — distinct from a fetch that
    reached it and got a bad response. Callers use this to distinguish
    "defer and self-heal next cycle" from a genuine data problem."""
