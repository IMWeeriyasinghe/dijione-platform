# Infrastructure and environments (verified read-only 2026-11-13)

Subscription: **Dijital Team IT Production** (`7d97cf51-…`), region Southeast Asia. Everything below was read
with `az ... show/list`; nothing was changed.

## Diji On-site Attendance — `rg-diji-onsite-attendance` (shared by DEV/UAT/PROD)

| Resource | Name / value |
|---|---|
| App Service plan | `asp-diji-onsite-attendance` (B1 Linux) |
| Ingestion API | `app-diji-onsite-attendance` → `https://app-diji-onsite-attendance.azurewebsites.net` (.NET 10, Always On, HTTPS only, system MI; `/healthz` 200) |
| Azure SQL | `sql-diji-onsite-attendance.database.windows.net` / `sqldb-diji-onsite-attendance` — Basic 5 DTU, geo backup, Entra-only auth, TLS 1.2, public network enabled with firewall |
| Firewall rules | `AllowAzureServices`, `ClientIPAddress_2026-11-03_23-10-04` (the Windows dev PC — **review/remove**, see BACKLOG) |
| Entra SQL admin | `sa-paymentslip@dijitalteam.com` |
| DB principals | `app-diji-onsite-attendance` (writer), `onsite-api-dijione-dev`, `-uat`, `-prod` (SELECT only) |
| Key Vault | `kv-diji-onsite-attend` (secret `site-key-dijital-lk-colombo-office` — the Agent's site API key) |
| App settings (names only) | `APPLICATIONINSIGHTS_CONNECTION_STRING`, `SCM_DO_BUILD_DURING_DEPLOYMENT`, `WEBSITE_HEALTHCHECK_MAXPINGFAILURES`; connection string `Ingestion` (SQLAzure, MI) |
| Monitoring | `log-diji-onsite-attendance`, `appi-diji-onsite-attendance` (sampled), alerts: backlog, errors, heartbeat, health, http5xx, failure anomalies |
| Site | `dijital-lk-colombo-office` "Dijital Team - Colombo Office", `Asia/Colombo`, active, epoch 1 |
| IaC | DijiOnsite-Agent repo `deploy/azure/attendance/main.bicep` + `deploy-attendance.ps1`, `register-site.ps1`, `grant-dijione-reader.ps1`, schema `services/DijiOnsiteAttendance.Ingestion/sql/schema.sql` |

The legacy `rg-diji-onsite-dev` was deleted after go-live. **Do not recreate it.**

## DijiOne environments

| | DEV | UAT | PROD |
|---|---|---|---|
| Resource group | `rg-dijione-dev` | `rg-dijione-uat` | `rg-dijione-prod` |
| Public URL | `dijione-dev.dijitalteam.com` | `dijione-uat.dijitalteam.com` | `dijione.dijitalteam.com` |
| Container Apps env | `cae-dijione-dev` | `cae-dijione-uat` | `cae-dijione-prod` |
| Registry | `crdijionenonprod` (`rg-dijione-shared`) | `crdijionenonprod` | `crdijioneprod` |
| PostgreSQL | `psql-dijione-dev` (db `onsite_dev`) | `psql-dijione-uat` (`onsite_uat`) | `psql-dijione-prod` (`onsite_prod`) |
| Key Vault | `kv-dijione-dev` | `kv-dijione-uat` | `kv-dijione-prod` |
| Shared UAMI | `id-dijione-dev` | `id-dijione-uat` | `id-dijione-prod` (AcrPull + Key Vault only) |
| onsite-api / onsite-web min replicas | 0 / 0 | 0 / 0 | **1 / 1** (PROD replica-floor decision) |
| `INTEGRATIONS_MODE` | live | live | live |
| Colombo site enabled in mirror | **yes** (dev-site disabled) | **no** | **unverified** |
| IaC | `main.bicep` + `main.dev.bicepparam` (`deployOnsite=true`) | `onsite-release.bicep` (On-site footprint) + `main.uat.bicepparam` | `onsite-release.bicep` + `main.prod.bicepparam` |

Per-environment On-site resources: apps `onsite-api`, `onsite-web`; jobs `onsite-sync-job`
(`* * * * *`, timeout 120 s), `migrate-onsite-api`, `people-workforce-sync-job` (`15 */6 * * *`); KV secret
`database-url-onsite`; onsite-api **system-assigned** MI = the SQL principal `onsite-api-dijione-<env>`.

### Deployed images (identical in all three, 2026-11-13)
| Image | Digest | Built from |
|---|---|---|
| onsite-api (+ `onsite-sync-job`, `migrate-onsite-api`) | `sha256:4e71488b4cb87539e71106f62f20a349e6e3fc459e2d3938c9b996ff818e727b` | release `5d93d42` (tag `px-5d93d42`) |
| onsite-web | `sha256:c156ba8c787fe3405e4e096a5f4474cd2c29f0fefe4cfb45d8dc5e517028fae1` | `5d93d42` |
| people-api (+ `migrate-people-api`) | `sha256:21b77405c4490744a3058799cbc48b491256a624e152ea546e2ec52acc871cb2` | `5d93d42` |
Other DijiOne apps (platform-api, shell-web, admin-web, Birthday, TalentFlow, DijiAtWork) are owned by other
workstreams and have since moved; do not redeploy them for On-site work.

Note: `people-workforce-sync-job` and `people-sync-job` still reference older people-api digests; they only run
`curl`, so this is cosmetic. `people-sync-job` (cron `30 18 * * *`) belongs to DijiBirthday — never touch it.

## Sync schedule — drift status

**Resolved.** Live cron is `* * * * *` in all three; repository defaults are `* * * * *` in both
`main.bicep` and `onsite-release.bicep` on `release/onsite-v1`. Live health 2026-11-13: 63–65 successful
runs/hour per environment, 1,439–1,440 per 24 h.

**Remaining risk:** `onsite-release.bicep` defaults to `onsiteIntegrationsMode='none'` and
`deployOnsiteSyncJob=false`, and there is no parameter file for it. A UAT/PROD redeploy **must** pass
`onsiteIntegrationsMode=live onsiteSqlServer=sql-diji-onsite-attendance.database.windows.net
onsiteSqlDatabase=sqldb-diji-onsite-attendance deployOnsiteSyncJob=true` (cron defaults to every minute) or it
will stop syncing. Recommended fix: add `onsite-release.uat.bicepparam` / `.prod.bicepparam` (BACKLOG).
Ad-hoc `az containerapp job update --image` keeps cron/timeout; it does **not** update `migrate-*` jobs
unless you update them too (`deploy/README.md`).
