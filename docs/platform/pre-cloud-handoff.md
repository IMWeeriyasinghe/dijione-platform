# DijiOne Pre-Cloud Handoff

Everything needed to take DijiOne from "complete locally" to a first Azure
DEV, consolidated in one place for whoever owns the Azure subscription and
Entra tenant. This document **names** resources, env vars, and secrets — it
does not create or configure any of them; nothing here has been provisioned.
Full step-by-step commands live in `deploy/README.md`; full topology detail
lives in `docs/platform/deployment-topology.md`; full ownership/dependency
detail lives in `docs/platform/data-ownership.md`. This document is the
index + checklist, not a fourth copy of the same content.

## 1. Azure resource inventory (none provisioned yet)

| Resource | Purpose |
|---|---|
| Resource group (`rg-dijione-dev`) | Container for everything below |
| Log Analytics workspace | Container Apps environment logs |
| Container Apps environment | Hosts every service below |
| Azure Database for PostgreSQL Flexible Server (Burstable B1ms, stoppable) | One server, one database per domain (§4) |
| Container Registry (GHCR free tier, or ACR Basic ~$5/mo) | Holds built images |
| Container Apps — one per service (§2) | The running workloads |
| Container Apps Jobs — 4 scheduled (§5) | Source sync + birthday scan triggers |
| Entra app registration | SSO (Easy Auth first cut, in-app OIDC as Wave 4b) |
| (Optional) Azure Front Door / API Management | Production path fan-out; dev uses `shell-web`'s own Next.js rewrites |

## 2. Container Apps service inventory + ingress matrix

| Service | Ingress | Target port | Min/Max replicas | Database |
|---|---|---|---|---|
| `shell-web` | **external** | 3000 | 1 / 3 | — |
| `birthday-supplier-web` | **external** (separate hostname) | 3000 | 0 / 2 | — |
| `admin-web` | internal | 3000 | 0 / 2 | — |
| `talent-web` | internal | 3000 | 0 / 2 | — |
| `birthday-web` | internal | 3000 | 0 / 2 | — |
| `platform-api` | internal | 8000 | 1 / 3 | `platform_dev` |
| `admin-api` | internal | 8000 | 0 / 2 | — (zero-DB BFF) |
| `talent-api` | internal | 8000 | 1 / 3 | `talent_dev` |
| `recruitment-api` | internal | 8000 | 0 / 2 | `recruitment_dev` |
| `people-api` | internal | 8000 | 0 / 2 | `people_dev` |
| `commercial-api` | internal | 8000 | 0 / 1 | `commercial_dev` (skeleton) |
| `birthday-api` | internal | 8000 | 0 / 2 | `birthday_dev` |
| `spark-api` | **not deployed** (skeleton — deliberate, see `deploy/README.md`) | — | — | — |

`platform-api`/`talent-api` keep `min-replicas=1` — a cold start on the
auth/workspace path is user-visible. Every other backend scales to zero.
Only `shell-web` and `birthday-supplier-web` take public traffic.

## 3. Deployment order

1. Provision the resource group, Log Analytics, Container Apps environment, PostgreSQL Flexible Server + databases (§4), registry, firewall rule.
2. Build + push every image (`deploy/build-push.sh`).
3. Create the Container Apps (internal ingress for every `*-api` and non-shell `*-web`, external for `shell-web`/`birthday-supplier-web`) with their env vars wired (§6) and secret *references* set (§7 — values set separately, never in a file).
4. Run the migration + catalog/demo seed job once (`scripts/bootstrap-dev.sh`, as a one-off Container Apps Job — §8, replacing the pre-Wave-G manual `scripts/seed.py` step now that the RBAC catalog is migration-seeded).
5. Create the two/four scheduled sync Jobs (§5).
6. Configure the Entra gate (§9).
7. Smoke test (§10).

## 4. PostgreSQL database inventory

One Flexible Server, one logical database per domain — never one shared
database, never a service reaching into another's:

| Database | Owning service |
|---|---|
| `platform_dev` | `platform-api` |
| `talent_dev` | `talent-api` |
| `recruitment_dev` | `recruitment-api` |
| `people_dev` | `people-api` (only if People/Birthday deployed) |
| `birthday_dev` | `birthday-api` (only if deployed) |
| `commercial_dev` | `commercial-api` (only if deployed — skeleton, one table today) |

`admin-api` and `spark-api` own no database.

## 5. Scheduled source-sync Jobs

| Job | Image | Cron (UTC) | Target |
|---|---|---|---|
| `recruitment-sync-job` | `recruitment-api` | `0 */6 * * *` | `POST /api/recruitment/internal/scheduled-sync` |
| `talent-reconcile-job` | `talent-api` | `15 */6 * * *` | `POST /api/talent/internal/recruitment/reconcile` |
| `people-sync-job` (opt) | `people-api` | `0 5 * * *` | `POST /api/people/internal/sync` |
| `birthday-scan-job` (opt) | `birthday-api` | `30 5 * * *` | `POST /api/birthday/internal/run-daily-scan` |

Each: `--parallelism 1`, `--replica-retry-limit 1`, `--replica-timeout
900-1800s`, authenticated with `X-Internal-Token` from the service's own
secret — never an in-process per-replica timer.

## 6. Service-to-service URLs (internal Container Apps DNS)

`http://<app-name>` resolves inside the Container Apps environment. The
full per-service required-env table (which upstream URL each service needs)
is in `deploy/README.md` §4 — not duplicated here to avoid two copies
drifting. Summary of the edges themselves: `talent-api → recruitment-api`,
`talent-api → platform-api`, `birthday-api → people-api`, `birthday-api →
platform-api`, `recruitment-api → platform-api`, `people-api →
platform-api`, `admin-api → platform-api` + `talent-api`, `shell-web →`
every backend + non-shell web app (gateway rewrites).

## 7. Secrets — NAMES ONLY (never values, never committed)

| Secret | Used by | Notes |
|---|---|---|
| `JWT_DEV_SECRET` | every backend | Must be identical, high-entropy, generated fresh for this environment — never the repo's dev default |
| `INTERNAL_SERVICE_SECRET` | every backend | Same — s2s trust anchor for `X-Internal-Token` |
| `DATABASE_URL` (per service) | every DB-owning service | Contains the PostgreSQL password — a secret in its own right |
| `ENTRA_CLIENT_SECRET` | `platform-api` (Wave 4b) / Entra app registration (Easy AUTH first cut) | From the Entra app registration |
| `LEVER_API_KEY` | `recruitment-api` | **Only if** this environment is deliberately configured for live discovery — `INTEGRATIONS_MODE=mock` otherwise. GET-only, never write-capable |
| `LEVER_WEBHOOK_SIGNING_SECRET` | `recruitment-api` | Only if a Lever webhook is registered against a reachable URL |
| `BAMBOOHR_API_KEY` / `BAMBOOHR_SUBDOMAIN` | `people-api` | Only if live BambooHR sync is configured |
| `HUBSPOT_ACCESS_TOKEN` | `commercial-api` | Not requested yet — remains blank; commercial-api has no live client to use it |
| `GRAPH_CLIENT_SECRET` (+ `GRAPH_TENANT_ID`/`GRAPH_CLIENT_ID`) | `birthday-api` | Only if `EMAIL_SENDING_MODE=live` |
| `AZURE_STORAGE_CONNECTION_STRING` | `talent-api` | Reserved for future real document upload (P2) — documents remain metadata-only until then |

Full per-service env var **names** (non-secret config too — URLs, modes,
CORS origins) are enumerated in each `apps/*/.env.example` — that is the
authoritative list; this table exists to flag which of those names hold
secrets.

## 8. Migration + catalog seeding order

1. `platform-api`: `alembic upgrade head` — this now includes the
   Wave-G-added catalog-seed migration
   (`f6a7b8c9d0e1_seed_authorization_catalog.py`), so the Admin Center is
   usable immediately after migration, before any demo-data seed script
   runs.
2. `talent-api`, `recruitment-api`, `people-api`, `commercial-api`,
   `birthday-api`: `alembic upgrade head` (any subset actually deployed).
3. `scripts/bootstrap-dev.sh` (or its two `seed.py --reset` calls run
   individually) — **demo data only** (dev personas, seeded
   clients/requests/candidates); skip this step for a real, non-demo
   environment.

Rollback: `alembic downgrade <previous-revision>` per service. Two
migrations are deliberately **irreversible by design** (`downgrade()`
raises `NotImplementedError`, not a bug):
`talent-api/alembic/versions/b8c9d0e1f2a3_*` (the Recruitment Source
re-key) and `c1d3e5f7a9b0_drop_hubspot_integration_tables.py` — both drop
tables nothing still reads; rolling them back would mean recreating tables
with no writer, not restoring lost data. A genuine rollback need on either
means restoring the pre-migration database backup, not `alembic
downgrade`.

## 9. Entra configuration checklist (user-owned action)

- Single-tenant Entra app registration, **Web** platform.
- Delegated scopes: `openid profile email`.
- One client secret (rotatable).
- Redirect URI: `https://<shell-web-fqdn>/api/auth/callback` — added
  **after** `shell-web`'s Container App exists and its hostname is known
  (step 6 of `deploy/README.md`).
- First cut: Container Apps built-in auth ("Easy Auth") on `shell-web`
  only, `AUTH_MODE=dev` (Dev Identity Mode) still active behind it.
- Wave 4b (after the first DEV works): `AUTH_MODE=entra` on `platform-api`
  itself, full in-app OIDC Authorization Code + PKCE flow, `ENTRA_TENANT_ID`
  / `ENTRA_CLIENT_ID` / `ENTRA_CLIENT_SECRET` / `ENTRA_REDIRECT_URI` /
  `PUBLIC_BASE_URL` set.
- No group-claim/app-role configuration is required for the first cut —
  DijiOne's own role/permission model stays authoritative; Entra only
  proves identity.

## 10. Smoke-test runbook

1. `for s in platform-api admin-api talent-api recruitment-api people-api commercial-api birthday-api; do curl .../health/deep; done` — every DB-owning service reports DB + migration-head + integration mode; `admin-api`/`spark-api` report liveness only.
2. Open `https://<shell-web-fqdn>` → Dev Identity Mode persona picker loads.
3. Sign in as `madushanka` (TA Member) → DijiOne Home renders, module cards show correct health badges.
4. Open DijiTalentFlow → TA Operations Dashboard loads with seeded data.
5. Open Admin Center → Users list renders with real client names (proves the platform-owned canonical Client identity path).
6. Trigger `recruitment-sync-job` manually once → `SUCCEEDED`, postings visible via `talent-web` `/postings`.
7. If People/Birthday deployed: trigger `people-sync-job` then `birthday-scan-job` manually once → both complete without error.
8. Kill (stop) `recruitment-api`'s revision → talent-api's postings screen still renders VERIFIED postings with a staleness note (fail-closed local-projection check — `docs/platform/data-ownership.md` §4a). Restart it.

## 11. UAT checklist (stakeholder-facing, once hosted DEV is up)

- [ ] Sign-in works for each seeded persona (client, TA, CS, TA manager, platform admin, super admin).
- [ ] Client Workspace: submit a request, see it move through CS review → TA stages, correct progress bar.
- [ ] TA Workspace: Operations Dashboard, Client Portfolios, Candidate Pool, Applications, Interview Manager all load with live data.
- [ ] Tenant isolation: a client persona cannot see another client's requests/candidates/postings by any route (list, detail, manipulated id, filter).
- [ ] Admin Center: user/role/module/client-scope management works; audit log records changes.
- [ ] DijiBirthday (if deployed): order lifecycle from detection through supplier dispatch works against a real people-api sync.
- [ ] No client-facing screen shows a raw provider payload, an internal id where a name is expected, or a broken/empty state where data should exist.
- [ ] Sign-off: stakeholder confirms the DTC-tag → client mapping resolves correctly against real Lever postings before any live (non-mock) recruitment-api cutover.

## 12. Cost-conscious configuration

Target operating envelope: **~USD 50-150/month**, matching the plan's
stated range (the deploy README's own quick estimate of $20-35/mo running,
~$10 with PostgreSQL stopped, is the *minimal first-cut* subset —
platform-api/admin-api/talent-api/recruitment-api/shell-web/admin-web/
talent-web only, no Birthday/Commercial/People). Levers, in order of
impact:

- Scale-to-zero on every backend except `platform-api`/`talent-api`
  (min-replicas=1 each) and every internal web zone.
- PostgreSQL Flexible Server B1ms (Burstable), stopped between demos —
  `az postgres flexible-server stop/start`.
- Container Registry: GHCR free tier over ACR unless already paying for
  ACR elsewhere.
- Deploy People/Birthday/Commercial only when actually needed
  (`DEPLOY_BIRTHDAY`/`DEPLOY_COMMERCIAL` flags in `provision.sh`/
  `build-push.sh`) — don't pay for idle capacity ahead of the feature
  actually being used.
- No Azure Front Door / API Management in the first cut — `shell-web`'s own
  Next.js rewrites already do the path fan-out; add Front Door only when a
  custom domain or WAF requirement justifies it.
- `spark-api` stays undeployed (true skeleton, zero business value yet).

## 13. Exact next external step

Everything above this line is **prepared, not executed.** The next action
requires the user: approve Azure spend, run `az login`, and either (a)
delegate `deploy/provision.sh` + `deploy/build-push.sh` to this agent to
execute against a real subscription, or (b) run them directly. Either way,
Docker must be available wherever the images are built — this development
environment currently has none, so Wave I's container-build verification
stayed at "Dockerfiles inspected and fixed, not `docker build`-executed"
(see the completion report).
