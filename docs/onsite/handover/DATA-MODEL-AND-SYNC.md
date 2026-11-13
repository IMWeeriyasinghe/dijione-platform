# Data model, ingestion, synchronization and reconciliation

## Event identity

`EventId = "<SiteId>:<SourceEpoch>:<SourceTransactionId>"`, e.g. `dijital-lk-colombo-office:1:46040`.
`SourceTransactionId` = ZKBioTime `iclock_transaction.id`. `SourceEpoch` increments only on an explicit
Agent re-baseline (never done in production; it would keep old events distinct, not overwrite them).
Uniqueness is enforced twice in Azure SQL: PK on `EventId` and `UQ (SiteId, SourceEpoch, SourceTransactionId)`;
the mirror's PK is `event_id` (insert-if-absent), so replays and overlapping syncs never duplicate.

## Authoritative store (Azure SQL, schema `onsite`) — owned by the Agent repo

Schema: `services/DijiOnsiteAttendance.Ingestion/sql/schema.sql` (DijiOnsite-Agent repo).

| Table | Purpose |
|---|---|
| `Sites` | SiteId, DisplayName, TimeZone, IsActive, CreatedUtc, ApiKeyHash (never read by DijiOne) |
| `AttendanceEvents` | raw events: EmpCode, EmpId, PunchTimeLocal (datetimeoffset), PunchTimeUtc, TimeZone, PunchState, VerifyType, terminal SN/alias, area, UploadTimeUtc (ZKBio), CapturedAtUtc (Agent clock), ReceivedUtc (SQL clock), BatchId, RecordHash |
| `Batches` | one row per accepted batch (+ result JSON, replay count) — not read by DijiOne |
| `AgentStatus` | latest heartbeat per site: version, health, epoch, HighWaterId, pending/dead-letter, last poll/delivery/error |

Indexes on `AttendanceEvents`: `PK_AttendanceEvents (EventId)`, `UQ_AttendanceEvents_Source`,
`IX_AttendanceEvents_Emp_Time (EmpCode, PunchTimeUtc)`, `IX_AttendanceEvents_Site_Time (SiteId, PunchTimeUtc)`,
`IX_AttendanceEvents_Received (ReceivedUtc, EventId) INCLUDE (SiteId, SourceEpoch)` — the last turns every
1-minute mirror read into an index seek (measured 9 logical reads vs ~4,125 before).

## Mirror (`onsite_<env>` PostgreSQL, owned by onsite-api; Alembic head `0001_onsite_initial`)

`source_sites`, `site_settings` (enabled flag, **fail-closed**: a new site is disabled), `attendance_events`
(raw columns verbatim + `site_local_date`, `tz_consistent`, `sync_run_id`, `mirrored_at`), `agent_status`,
`onsite_sync_runs` (durable run state, reconciliation JSON), `sync_state` (single-row high-water mark).
Summaries (first/latest/count/flags) are computed on read — nothing derived is persisted.

## Mirror sync (`apps/onsite-api/app/services/mirror_sync_service.py`)

- Trigger: ACA job `onsite-sync-job`, cron `* * * * *` (UTC), replica timeout 120 s, which only `curl`s
  `POST http://onsite-api/api/onsite/internal/scheduled-sync` with the internal token; or "Sync now"
  (`POST /api/onsite/sync`, permission `onsite.sync.request`). Both use the same path.
- Single-flight: run creation serialized with `pg_advisory_xact_lock`; an existing QUEUED/RUNNING run is
  returned instead of starting another; a run older than 10 min is marked FAILED "Abandoned" so it can never
  block later ticks.
- Incremental: keyset pages of 5,000 ordered by `(ReceivedUtc, EventId)` from `high_water − 10 min`;
  insert-if-absent; per-page commit; high-water advanced. Never deletes.
- Source failures: connection retries ~90 s, then FAILED with `source_unavailable`; mirror untouched; next tick
  resumes from the same high-water. No data loss, no reimport.
- Reconciliation: per `(SiteId, SourceEpoch)` count + max ReceivedUtc, when a tick inserted rows, else every
  15 min. Mirror rows the source no longer reports are flagged, never deleted.
- Freshness: Delayed = no successful sync for 5 min or Agent pending>0; Stale = heartbeat > 10 min; Source
  unavailable = latest run failed on the source.

### Recovering a delayed mirror (no historical reimport)
1. Check `onsite-sync-job` executions (`az containerapp job execution list ...`) and Site Health.
2. If runs fail with source unavailable: check Azure SQL status/firewall/identity; nothing to repair in the mirror.
3. If a run is stuck RUNNING: it is auto-abandoned after 10 min; next tick proceeds.
4. "Sync now" (admin) or wait one minute. The high-water + 10-min overlap catches up automatically.
Never truncate the mirror or reset `sync_state` to "catch up" — that would re-read everything (allowed but
unnecessary; insert-if-absent keeps it correct).

## Historical milestones (historical, not live)

| Milestone | Value |
|---|---|
| Historical import (DEV, `dev-site`, epoch 1000) | 42,864 events, max tx 42881 |
| Production Agent start position | `after-id:42881` (never rebaselined) |
| 2026-11-03 verification | 44,938 events, max tx 44958 |
| **2026-11-13 16:07 UTC (live check)** | **46,019 events, tx 1 → 46040, 0 duplicates**, mirrors in DEV and UAT equal; PROD not readable from Windows |

The `dev-site` rows (42,871: epoch 1000 + 7 test events) exist only in the **DEV** mirror, from the retired
DEV stack; `dev-site` is disabled there. They are not in the authoritative store.

## Read-only verification commands

Authoritative store (needs your own Entra login with access; firewall must allow your IP — see SECURITY):
```sql
SELECT SiteId, SourceEpoch, COUNT_BIG(*) events, MAX(SourceTransactionId) max_tx, MAX(ReceivedUtc) last_received
FROM onsite.AttendanceEvents GROUP BY SiteId, SourceEpoch;
SELECT COUNT_BIG(*) - COUNT_BIG(DISTINCT EventId) AS dup FROM onsite.AttendanceEvents;
SELECT SiteId, AgentVersion, Health, HighWaterId, PendingCount, DeadLetterCount, LastHeartbeatUtc, LastDeliveryUtc,
       DATEDIFF(second, LastHeartbeatUtc, SYSUTCDATETIME()) hb_age_s FROM onsite.AgentStatus;
```
(`sqlcmd -S sql-diji-onsite-attendance.database.windows.net -d sqldb-diji-onsite-attendance --authentication-method ActiveDirectoryAzCli`;
on macOS install `go-sqlcmd` via Homebrew.)

Mirror sync health without touching data:
```bash
az containerapp job execution list -g rg-dijione-<env> -n onsite-sync-job --query "[0:10].[properties.status,properties.startTime]" -o tsv
```
Mirror contents: Site Health page (admin) or the read-only exec pattern in VALIDATION-CHECKLIST.md
(blocked for PROD by policy — use the UI there).
