# Diji On-site — deployment

Diji On-site is deployed by the standard DijiOne Bicep (`deploy/bicep/`)
behind its own flag, so it can be deployed or removed without touching any
other application module.

## Flags and parameters

| Parameter | Where | Meaning |
|---|---|---|
| `deployOnsite` | `foundation.bicep`, `main.bicep` (default `false`) | `onsite_<env>` database + Key Vault secret name; `onsite-api`, `onsite-web`, `migrate-onsite-api`, `onsite-sync-job` |
| `deployPeople` (derived) | both | `deployBirthday \|\| deployOnsite` — the shared People source domain is deployed for any consumer |
| `onsiteIntegrationsMode` | `main.bicep` | `mock` (default) or `live` (Azure SQL `onsite.*`, SELECT-only, managed identity) |
| `onsiteSqlServer`, `onsiteSqlDatabase` | `main.bicep` | Azure SQL source host and database (live mode only) |
| `onsiteSyncCron` | `main.bicep`, `onsite-release.bicep` | `onsite-sync-job` schedule (UTC); `* * * * *` in every environment — see "Refresh cadence" |

`people-workforce-sync-job` (`15 */6 * * *`) runs whenever People is
deployed. The Birthday `people-sync-job` stays gated by `deployBirthday`,
unchanged. Scripts read `DEPLOY_ONSITE=true` the same way they read
`DEPLOY_BIRTHDAY`.

DEV sets `deployOnsite = true` in `main.dev.bicepparam`; UAT and PROD run the
On-site footprint through `deploy/bicep/onsite-release.bicep`. All three use
`onsiteIntegrationsMode = live` against the **same** source:

| Setting | Value (every environment) |
|---|---|
| `onsiteSqlServer` | `sql-diji-onsite-attendance.database.windows.net` |
| `onsiteSqlDatabase` | `sqldb-diji-onsite-attendance` |
| SQL user | `onsite-api-dijione-<env>` (SELECT only) |
| Mirror | `onsite_<env>` (environment-specific, derived) |

Diji On-site Attendance (resource group `rg-diji-onsite-attendance`) is owned
by the Diji On-site Agent repository (`deploy/azure/attendance/`); DijiOne
never writes to it.

## Refresh cadence (near-real-time)

Target: a fingerprint punch is visible on the Diji On-site dashboard within
**~1–2 minutes** under normal operation.

| Stage | Cadence | Where it is set |
|---|---|---|
| Diji On-site Agent polls ZKBioTime (SELECT-only) | every `Source.PollIntervalSeconds` (default 10 s); loops at once while catching up | Agent `appsettings` / Settings UI |
| Agent → Diji On-site Attendance (ingestion API) | delivery is triggered right after each capture; SQLite outbox with backoff retries; heartbeat every 60 s | Agent `Ingestion.*` options |
| Diji On-site Attendance → `onsite_<env>` mirror | every minute: `onsite-sync-job` cron `* * * * *` (Container Apps Jobs evaluate cron in UTC) | `onsiteSyncCron` (Bicep) |
| Dashboard refetch | every 30 s while the tab is visible, and immediately when it becomes visible again | `apps/onsite-web/src/lib/live-refresh.ts` |
| "Sync now" | on demand (`onsite.sync.request`, On-site Admin) | Site Health / Overview |

Expected delay = Agent poll (≤10 s) + delivery (seconds) + wait for the next
mirror tick (≤60 s) + sync run (seconds) + dashboard refetch (≤30 s), i.e.
typically 30–100 s, worst case about 2 minutes. "Sync now" is not needed for
routine operation.

**How the one-minute sync stays safe and cheap**

- The job only POSTs the internal `scheduled-sync` endpoint (internal token;
  never public) and exits; the run executes inside `onsite-api`. Job replica
  timeout is 120 s, so stuck executions cannot pile up.
- Single-flight across replicas: run creation is serialized with a
  PostgreSQL advisory lock; while a run is QUEUED/RUNNING every other request
  (scheduled or "Sync now") gets that run back (`started: false`).
- A run left QUEUED/RUNNING for more than 10 minutes (its replica stopped
  mid-run, e.g. a revision swap) is marked FAILED ("Abandoned") so it never
  blocks later syncs. The mirror is untouched by this.
- Incremental only: keyset reads from the high-water `ReceivedUtc` minus a
  10-minute overlap, so a tick reads only the last few minutes of events.
  Insert-if-absent by `EventId` (primary key) — repeated or overlapping ticks
  can never duplicate rows; nothing is ever deleted.
- Source-vs-mirror reconciliation (a per-epoch aggregate on Azure SQL) runs
  whenever a tick inserted rows and otherwise at most every 15 minutes.
- Azure SQL failures: connection retries with backoff for up to 90 s; then
  the run is FAILED with `source_unavailable`, the mirror is kept, and the
  next tick resumes from the same high-water mark — no data is lost.
- The authoritative database stays SELECT-only for every DijiOne consumer;
  each environment (DEV/UAT/PROD) keeps its own derived `onsite_<env>`
  mirror and its own sync state.

**Freshness indicator.** Every attendance page shows, separately: when the
page last refreshed ("Updated just now / 30 seconds ago"), when DijiOne last
mirrored the source ("Last synced 2 minutes ago"), and the feed state. "Data
may be delayed" appears whenever the feed is not current — a successful page
refresh is never shown as proof the source is current. A failed refresh keeps
the last loaded data and says so; "Refresh" refetches on demand.

Feed states: **Delayed** when the last successful mirror sync is older than
5 minutes or the Agent reports pending deliveries; **Stale** when the Agent
heartbeat is older than 10 minutes; **Source unavailable** when the latest
sync could not reach Azure SQL.

**Monitoring.** Watch `onsite-sync-job` executions (expect one per minute,
all Succeeded), the Site Health page (latest run, reconciliation, Agent
pending/dead-letter counts), and `onsite-api` logs for
`onsite mirror sync … failed` / `abandoned`. Alert when no successful sync
for 10 minutes or the feed is Stale. This cadence is a documented deviation
from the 6-hour default in CLAUDE.md rule 10, still using the replica-safe
scheduled Job.

**Cost.** ~1,440 job executions/day per environment, each a short `curl`
container (seconds of 0.25 vCPU) — inside or near the Container Apps free
grant. Because the job calls `onsite-api` every minute, `onsite-api` no
longer scales to zero; that always-on replica is the main cost increase.
Azure SQL load per tick is a single indexed-range read of a few minutes of
events plus small `Sites`/`AgentStatus` reads.

## Images

`deploy/Dockerfile.api` installs Microsoft ODBC Driver 18 and unixODBC only
when a service's `requirements.txt` lists `pyodbc` (today only
`onsite-api`), and verifies at build time that the driver loads. Every
other API image is built exactly as before.

## Source access (Azure SQL)

`onsite-api` authenticates with its own **system-assigned** managed identity
(`DefaultAzureCredential`). It never uses a SQL password, the shared
`id-dijione-<env>` UAMI, or the ingestion API's identity. The On-site SQL
Entra admin runs `docs/onsite/sql-principal.sql` (SELECT only on the approved
tables/columns; no `Batches`, no `ApiKeyHash`), or equivalently the Agent
repository's `deploy/azure/attendance/grant-dijione-reader.ps1 -Env <env>`.

## First deployment sequence (per environment)

1. Database `onsite_<env>` and Key Vault secret `database-url-onsite`.
2. Build images (`DEPLOY_ONSITE=true deploy/build-images.sh …`).
3. Deploy with `onsiteIntegrationsMode=mock`; run `migrate-onsite-api`;
   smoke test.
4. SQL Entra admin runs `sql-principal.sql` with onsite-api's principal id.
5. Switch to `onsiteIntegrationsMode=live`; "Sync now"; verify reconciliation.
6. Enable the site from On-site Admin → Sites (never by configuration).

Removal: `docs/onsite/module-removal.md`.
