"""Live Azure SQL client (SELECT-only) for the ``onsite`` schema.

Auth: an Entra access token from ``DefaultAzureCredential`` — in Azure this
is onsite-api's own system-assigned managed identity; locally it is the
developer's ``az login``. Never a SQL password. The token is passed through
the ODBC ``SQL_COPT_SS_ACCESS_TOKEN`` pre-connect attribute.

Connection attempts are retried for a bounded window
(``sync_source_retry_seconds``, ~90 s) to absorb a serverless resume; after
that ``SourceUnavailableError`` is raised and the caller keeps the previous
mirror intact.
"""

from __future__ import annotations

import logging
import struct
import time
from datetime import datetime

import pyodbc

from app.attendance_source import queries
from app.attendance_source.client import (
    OnsiteSourceClient,
    SourceAgentStatusRow,
    SourceEpochTotals,
    SourceEventRow,
    SourceSiteRow,
    SourceUnavailableError,
)
from app.core.config import get_settings

logger = logging.getLogger("onsite-api.attendance_source")

SQL_COPT_SS_ACCESS_TOKEN = 1256
_TOKEN_SCOPE = "https://database.windows.net/.default"


def _token_struct(token: str) -> bytes:
    raw = token.encode("utf-16-le")
    return struct.pack(f"<I{len(raw)}s", len(raw), raw)


class OnsiteSqlClient(OnsiteSourceClient):
    def __init__(self) -> None:
        settings = get_settings()
        if not (settings.onsite_sql_server and settings.onsite_sql_database):
            raise SourceUnavailableError("ONSITE_SQL_SERVER and ONSITE_SQL_DATABASE must be set for live mode")
        self._conn_str = (
            "Driver={ODBC Driver 18 for SQL Server};"
            f"Server=tcp:{settings.onsite_sql_server},1433;"
            f"Database={settings.onsite_sql_database};"
            "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
            "ApplicationIntent=ReadOnly;"
        )
        self._retry_seconds = settings.sync_source_retry_seconds
        self._conn: pyodbc.Connection | None = None
        self._credential = None

    def _connect(self) -> pyodbc.Connection:
        if self._conn is not None:
            return self._conn
        from azure.identity import DefaultAzureCredential

        if self._credential is None:
            self._credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        deadline = time.monotonic() + self._retry_seconds
        delay = 5.0
        last: Exception | None = None
        while True:
            try:
                token = self._credential.get_token(_TOKEN_SCOPE).token
                self._conn = pyodbc.connect(
                    self._conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: _token_struct(token)}, readonly=True,
                )
                return self._conn
            except Exception as exc:  # noqa: BLE001 - classify after retries
                last = exc
                if time.monotonic() + delay > deadline:
                    break
                logger.info("onsite source connect failed (%s); retrying in %.0fs", exc.__class__.__name__, delay)
                time.sleep(delay)
                delay = min(delay * 1.5, 20.0)
        raise SourceUnavailableError(f"Azure SQL onsite source unavailable: {last.__class__.__name__}") from last

    def _rows(self, sql: str, *params) -> list[pyodbc.Row]:
        try:
            cur = self._connect().cursor()
            cur.execute(sql, *params)
            return cur.fetchall()
        except SourceUnavailableError:
            raise
        except pyodbc.OperationalError as exc:
            self.close()
            raise SourceUnavailableError(f"Azure SQL onsite source error: {exc.__class__.__name__}") from exc

    def list_sites(self) -> list[SourceSiteRow]:
        return [
            SourceSiteRow(site_id=r.SiteId, display_name=r.DisplayName, time_zone=r.TimeZone,
                          is_active=bool(r.IsActive), created_utc=r.CreatedUtc)
            for r in self._rows(queries.SITES)
        ]

    def read_events_after(self, received_after: datetime | None, event_id_after: str, limit: int) -> list[SourceEventRow]:
        if received_after is None:
            rows = self._rows(queries.EVENTS_FROM_START, limit)
        else:
            rows = self._rows(queries.EVENTS_AFTER_CURSOR, limit, received_after, received_after, event_id_after)
        return [
            SourceEventRow(
                event_id=r.EventId, site_id=r.SiteId, source_epoch=int(r.SourceEpoch),
                source_transaction_id=int(r.SourceTransactionId), emp_code=r.EmpCode, emp_id=r.EmpId,
                punch_time_local=r.PunchTimeLocal, punch_time_utc=r.PunchTimeUtc, time_zone=r.TimeZone,
                punch_state=r.PunchState, verify_type=r.VerifyType, work_code=r.WorkCode,
                terminal_sn=r.TerminalSn, terminal_alias=r.TerminalAlias, area_alias=r.AreaAlias,
                source=r.Source, is_attendance=None if r.IsAttendance is None else bool(r.IsAttendance),
                upload_time_utc=r.UploadTimeUtc, captured_at_utc=r.CapturedAtUtc, received_utc=r.ReceivedUtc,
                batch_id=r.BatchId, record_hash=r.RecordHash,
            )
            for r in rows
        ]

    def list_agent_status(self) -> list[SourceAgentStatusRow]:
        return [
            SourceAgentStatusRow(
                site_id=r.SiteId, agent_instance_id=r.AgentInstanceId, agent_version=r.AgentVersion,
                health=r.Health, health_reason=r.HealthReason, source_epoch=int(r.SourceEpoch),
                high_water_id=r.HighWaterId, source_connected=bool(r.SourceConnected),
                last_source_poll_utc=r.LastSourcePollUtc, last_delivery_utc=r.LastDeliveryUtc,
                pending_count=int(r.PendingCount), dead_letter_count=int(r.DeadLetterCount),
                oldest_pending_age_seconds=r.OldestPendingAgeSeconds, last_error=r.LastError,
                last_heartbeat_utc=r.LastHeartbeatUtc, heartbeat_count=int(r.HeartbeatCount),
            )
            for r in self._rows(queries.AGENT_STATUS)
        ]

    def epoch_totals(self) -> list[SourceEpochTotals]:
        return [
            SourceEpochTotals(site_id=r.SiteId, source_epoch=int(r.SourceEpoch),
                              event_count=int(r.EventCount), max_received_utc=r.MaxReceivedUtc)
            for r in self._rows(queries.EPOCH_TOTALS)
        ]

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
