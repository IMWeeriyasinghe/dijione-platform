# System architecture and data flow

```
ZKTeco terminal (SN CQZ7232560569, alias "Office")
   │ pushes punches (ZKTeco protocol) — Diji never talks to the device
   ▼
ZKBioTime on production PC DESKTOP-V3H5OFI
   PostgreSQL 127.0.0.1:7496 / biotime  — public.iclock_transaction, personnel_employee, personnel_department
   │ SELECT only, role diji_onsite_reader, forced read-only session, short lock/statement timeouts
   ▼
Diji On-site Agent (Windows service DijiOnsiteAgent, NT SERVICE\DijiOnsiteAgent)
   capture every 10 s → atomic checkpoint+outbox commit (SQLite agent.db) → delivery worker
   │ HTTPS POST /api/onsite-agent/v1/attendance-batches  (Bearer site key, X-Diji-Site-Id, X-Diji-Agent-Version,
   │                                                      Idempotency-Key; contract contracts/ingestion-v1/openapi.yaml)
   │ HTTPS POST /api/onsite-agent/v1/heartbeats          (every 60 s)
   ▼
Diji On-site Attendance — app-diji-onsite-attendance (App Service, .NET 10, Always On)
   validates site key (hash in onsite.Sites), inserts (dedupe on EventId + UQ source key), records Batches/AgentStatus
   │ system-assigned MI → Azure SQL (writer)
   ▼
Azure SQL sqldb-diji-onsite-attendance (Basic 5 DTU, Entra-only)   ← the ONE authoritative store
   │ SELECT only — contained users onsite-api-dijione-dev / -uat / -prod (each env's onsite-api system MI)
   ▼
DijiOne onsite-api (DEV / UAT / PROD separately)
   onsite-sync-job (ACA job, cron * * * * *) → POST /api/onsite/internal/scheduled-sync → MirrorSyncService
   incremental keyset read (ReceivedUtc, EventId) from high-water − 10 min, insert-if-absent
   ▼
onsite_<env> PostgreSQL mirror (environment-specific, derived)   + people-api Workforce Directory (HTTP)
   ▼
onsite-api read APIs (/api/onsite/*) — JWT module_roles.onsite permissions + enabled-site allow-list
   ▼
onsite-web (Next.js, basePath /onsite, behind shell-web gateway) — TanStack Query, refetch every 30 s
```

## Writers vs readers

| Component | Reads | Writes |
|---|---|---|
| ZKBioTime / terminal | — | its own DB (not ours) |
| Diji On-site Agent | ZKBioTime (SELECT only) | its local `agent.db` (checkpoint, outbox), logs |
| Diji On-site Attendance | its DB | `onsite.AttendanceEvents`, `Batches`, `AgentStatus` (only writer of the authoritative DB) |
| DijiOne onsite-api | authoritative DB (SELECT only), people-api, platform-api | its own `onsite_<env>` mirror only |
| people-api | BambooHR (read) | `people_<env>` (Workforce Directory incl. `photo_url`) |
| platform-api | — | registry, roles, audit |

## Boundaries (enforced)

- Only `apps/onsite-api/app/attendance_source/` may talk to Azure SQL (`test_no_direct_onsite_sql_dependency.py`).
- No other DijiOne module references On-site; guard `scripts/check-module-independence.js` + CI
  `module-boundaries.yml`. Removal procedure: `docs/onsite/module-removal.md`.
- People data only through people-api's Workforce Directory contract (`auth_client_py.WorkforceDirectoryClient`),
  never the People database; DijiBirthday's employee contract is untouched.

## Timing (measured 2026-11-03, re-checked 2026-11-13)

| Stage | Observed |
|---|---|
| punch → ZKBioTime row | 4–5 s |
| ZKBioTime → Agent capture | 1–9 s (poll 10 s) |
| Agent → Azure `ReceivedUtc` | appears as ~62–66 s, **but** the Agent's own `LastDeliveryUtc` (14:17:36) precedes Azure's receipt (14:18:42) by 66 s on 2026-11-13 — physically impossible unless the **production PC clock is ~1 minute slow**. Most likely root cause: PC clock skew, not delivery latency. Needs `w32tm /query /status` on the PC (BACKLOG). |
| Azure → mirror | ≤ 60 s + ~0.6 s run |
| mirror → dashboard | ≤ 30 s |

Details of each stage, failure handling and recovery: [DATA-MODEL-AND-SYNC.md](DATA-MODEL-AND-SYNC.md),
[AGENT-OPERATIONS.md](AGENT-OPERATIONS.md).
