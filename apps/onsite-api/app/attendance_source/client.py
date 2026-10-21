"""OnsiteSourceClient — the read-only seam between Diji On-site and the
Azure SQL ``onsite`` schema owned by the separate ingestion plane.

This package (``app/attendance_source/``) is the ONLY code in DijiOne
allowed to reach Azure SQL ``onsite.*`` (static guard:
``tests/test_no_direct_onsite_sql_dependency.py``). Never writes, never DDL,
never reads ``onsite.Batches`` or ``onsite.Sites.ApiKeyHash``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


class SourceUnavailableError(Exception):
    """The source could not be reached (connection/timeout/paused DB) after
    the bounded retry window. The previous mirror stays intact."""


@dataclass(frozen=True)
class SourceSiteRow:
    site_id: str
    display_name: str
    time_zone: str
    is_active: bool
    created_utc: datetime | None


@dataclass(frozen=True)
class SourceEventRow:
    """One ``onsite.AttendanceEvents`` row, values exactly as read."""

    event_id: str
    site_id: str
    source_epoch: int
    source_transaction_id: int
    emp_code: str
    emp_id: int | None
    punch_time_local: str  # ISO-8601 with offset, verbatim
    punch_time_utc: datetime  # naive UTC
    time_zone: str
    punch_state: str | None
    verify_type: int | None
    work_code: str | None
    terminal_sn: str | None
    terminal_alias: str | None
    area_alias: str | None
    source: int | None
    is_attendance: bool | None
    upload_time_utc: datetime | None
    captured_at_utc: datetime
    received_utc: datetime  # naive UTC
    batch_id: str
    record_hash: str


@dataclass(frozen=True)
class SourceAgentStatusRow:
    site_id: str
    agent_instance_id: str | None
    agent_version: str | None
    health: str
    health_reason: str | None
    source_epoch: int
    high_water_id: int | None
    source_connected: bool
    last_source_poll_utc: datetime | None
    last_delivery_utc: datetime | None
    pending_count: int
    dead_letter_count: int
    oldest_pending_age_seconds: float | None
    last_error: str | None
    last_heartbeat_utc: datetime
    heartbeat_count: int


@dataclass(frozen=True)
class SourceEpochTotals:
    site_id: str
    source_epoch: int
    event_count: int
    max_received_utc: datetime | None


class OnsiteSourceClient(ABC):
    @abstractmethod
    def list_sites(self) -> list[SourceSiteRow]: ...

    @abstractmethod
    def read_events_after(
        self, received_after: datetime | None, event_id_after: str, limit: int
    ) -> list[SourceEventRow]:
        """Keyset page ordered by ``(ReceivedUtc, EventId)`` strictly after
        the cursor. ``received_after=None`` starts from the beginning."""
        ...

    @abstractmethod
    def list_agent_status(self) -> list[SourceAgentStatusRow]: ...

    @abstractmethod
    def epoch_totals(self) -> list[SourceEpochTotals]: ...

    def close(self) -> None:  # noqa: B027 - optional hook
        """Release any open connection (no-op by default)."""
