"""BambooHRClient interface. ``app/integrations/bamboohr/http_client.py``
is the real implementation (live-verified 2026-08-14 against the
``dijitalteam`` tenant, read-only Custom Report calls only). Never write to
BambooHR."""

from abc import ABC, abstractmethod

from app.integrations.bamboohr.schemas import BambooHREmployee


class BambooHRClient(ABC):
    @abstractmethod
    def list_active_employees(self) -> list[BambooHREmployee]: ...

    @abstractmethod
    def get_employee(self, employee_id: str) -> BambooHREmployee | None:
        """Single-employee lookup by BambooHR internal ``id`` — used by the
        employee_number backfill script, not by the daily scan."""
        ...


class BambooHRNotConfiguredError(Exception):
    """Raised by a future live BambooHRClient when no API key is configured."""


class BambooHRFetchError(Exception):
    """Raised when a BambooHR directory fetch fails (network/auth/5xx from
    the provider). Callers must catch this and record an audit event
    (no PII) rather than letting employee data leak into an error message."""
