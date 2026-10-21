"""The only T-SQL in DijiOne for the Azure SQL ``onsite`` schema.

SELECT-only. Column lists are explicit: ``onsite.Sites.ApiKeyHash`` is never
selected and ``onsite.Batches`` is never read. ``PunchTimeLocal``
(datetimeoffset) is rendered as its own local wall-clock time plus its own
offset (e.g. ``2025-09-18T16:57:33+05:30``) so it is mirrored verbatim. Do NOT
use CONVERT style 127: it normalizes a datetimeoffset to UTC (``...Z``).
"""

SITES = """
SELECT SiteId, DisplayName, TimeZone, IsActive, CreatedUtc
FROM onsite.Sites
"""

_EVENT_COLUMNS = """
    EventId, SiteId, SourceEpoch, SourceTransactionId, EmpCode, EmpId,
    CONVERT(varchar(19), CAST(PunchTimeLocal AS datetime2(0)), 126)
        + DATENAME(TZOFFSET, PunchTimeLocal) AS PunchTimeLocal,
    PunchTimeUtc, TimeZone, PunchState, VerifyType, WorkCode, TerminalSn,
    TerminalAlias, AreaAlias, Source, IsAttendance, UploadTimeUtc,
    CapturedAtUtc, ReceivedUtc, BatchId, RecordHash
"""

EVENTS_FROM_START = f"""
SELECT TOP (?) {_EVENT_COLUMNS}
FROM onsite.AttendanceEvents
ORDER BY ReceivedUtc, EventId
"""

EVENTS_AFTER_CURSOR = f"""
SELECT TOP (?) {_EVENT_COLUMNS}
FROM onsite.AttendanceEvents
WHERE ReceivedUtc > ? OR (ReceivedUtc = ? AND EventId > ?)
ORDER BY ReceivedUtc, EventId
"""

AGENT_STATUS = """
SELECT SiteId, AgentInstanceId, AgentVersion, Health, HealthReason, SourceEpoch,
       HighWaterId, SourceConnected, LastSourcePollUtc, LastDeliveryUtc,
       PendingCount, DeadLetterCount, OldestPendingAgeSeconds, LastError,
       LastHeartbeatUtc, HeartbeatCount
FROM onsite.AgentStatus
"""

EPOCH_TOTALS = """
SELECT SiteId, SourceEpoch, COUNT_BIG(*) AS EventCount, MAX(ReceivedUtc) AS MaxReceivedUtc
FROM onsite.AttendanceEvents
GROUP BY SiteId, SourceEpoch
"""
