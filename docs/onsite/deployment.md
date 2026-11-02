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
| `onsiteSyncCron` | `main.bicep` | `onsite-sync-job` schedule; DEV `0 */6 * * *` |

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
