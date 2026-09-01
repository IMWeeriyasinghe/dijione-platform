# DijiOne Deployment Topology (Azure Container Apps)

> Target topology for the shared DEV / production-like environment
> (Architecture Completion Plan Wave D). **Nothing here is provisioned yet** —
> `deploy/provision.sh` creates it; this document is the reference the
> provisioning script and the pre-cloud handoff (`deploy/README.md`) follow.
> Cost envelope: ~USD 50–150/month on Burstable compute + PostgreSQL B1ms.

## Services

| Service | Kind | Ingress | Target port | Min/Max replicas | Database |
|---|---|---|---|---|---|
| `shell-web` | Next.js (standalone) | **external** (the only one) | 3000 | 1 / 3 | — |
| `admin-web` | Next.js | internal | 3000 | 0 / 2 | — |
| `talent-web` | Next.js | internal | 3000 | 0 / 2 | — |
| `birthday-web` | Next.js | internal | 3000 | 0 / 2 | — |
| `birthday-supplier-web` | Next.js | **external** (separate hostname) | 3000 | 0 / 2 | — |
| `platform-api` | FastAPI | internal | 8000 | 1 / 3 | `platform_dev` |
| `admin-api` | FastAPI (zero-DB BFF) | internal | 8000 | 0 / 2 | — |
| `talent-api` | FastAPI | internal | 8000 | 1 / 3 | `talent_dev` |
| `recruitment-api` | FastAPI (source domain — Lever) | internal | 8000 | 0 / 2 | `recruitment_dev` |
| `people-api` | FastAPI (source domain — BambooHR) | internal | 8000 | 0 / 2 | `people_dev` |
| `commercial-api` | FastAPI skeleton (HubSpot, deferred) | internal | 8000 | 0 / 1 | `commercial_dev` (later) |
| `birthday-api` | FastAPI | internal | 8000 | 0 / 2 | `birthday_dev` |
| `spark-api` | FastAPI skeleton | internal | 8000 | 0 / 1 | — |

`platform-api` / `talent-api` keep `min-replicas = 1` because a cold start on
the authorization / workspace path is user-visible; every other backend can
scale to zero.

## External vs internal ingress

Only **`shell-web`** (the DijiOne gateway) and **`birthday-supplier-web`**
(the external supplier portal, a deliberately separate hostname) accept
public traffic. Everything else is `--ingress internal` and reachable only
from inside the Container Apps environment. Production routes the browser to
the internal web zones and `/api/*` prefixes through Azure Front Door / API
Management doing the same path fan-out that `shell-web`'s Next.js rewrites do
in dev (see `docs/platform/service-contracts.md` "Gateway / routing").

## Databases (one per domain, PostgreSQL Flexible Server B1ms)

`platform_dev` · `talent_dev` · `recruitment_dev` · `people_dev` ·
`birthday_dev` · `commercial_dev` (when Commercial/CRM is built).

`admin-api`, `spark-api` own no database. No service connects to another
service's database — cross-domain reads go over HTTP contracts.

Local dev + the `api` / `migrations` CI workflows run on SQLite for speed;
the `postgres` CI workflow runs migrations + the full suite against
`postgres:16` for each DB-owning service, which is the same engine as
production.

## Scheduled source-sync Jobs (Container Apps Jobs — replica-safe, NOT in-process timers)

| Job | Image | Cron (UTC) | Does |
|---|---|---|---|
| `recruitment-sync-job` | `recruitment-api` | `0 */6 * * *` | `POST recruitment-api/api/recruitment/internal/scheduled-sync` — reconcile Lever every 6h |
| `talent-reconcile-job` | `talent-api` | `15 */6 * * *` | `POST talent-api/api/talent/internal/recruitment/reconcile` — refresh the posting projection + DTC trust reconciliation, 15 min after the recruitment sync |
| `people-sync-job` | `people-api` | `0 5 * * *` | `POST people-api/api/people/internal/sync` — reconcile BambooHR daily (its approved cadence — birthday detection is date-bound, not stream-like) |
| `birthday-scan-job` | `birthday-api` | `30 5 * * *` | `POST birthday-api/api/birthday/internal/run-daily-scan` — daily birthday detection from the People read model |

Each Job: `--parallelism 1`, `--replica-retry-limit 1`, `--replica-timeout`
900–1800s, `X-Internal-Token` from the app secret. A Job failure leaves the
previous good read model intact; a scheduled failure surfaces to
`TA_MANAGER` / `BIRTHDAY_ADMIN` operationally, a scheduled success is silent.

## Health probes

Every service exposes `GET /health` (liveness) and `GET /health/deep`
(readiness). `/health/deep`:

- DB-owning services: `SELECT 1` + applied `alembic_version` + integration
  mode(s).
- `platform-api`: also a **local** client-scope integrity join
  (`client_ref` -> `clients.public_id`).
- `talent-api`: also a **non-fatal** `recruitment_source` reachability line —
  a source outage reads `degraded`, never fails readiness.
- `admin-api`: **non-fatal** reachability of `platform-api` + `talent-api`
  (zero-DB BFF).
- `spark-api`: liveness shape only (skeleton).

Configure the Container Apps readiness probe against `/health/deep` and the
liveness probe against `/health`.

## Service-to-service auth

Dev/DEV: the shared `INTERNAL_SERVICE_SECRET` on `X-Internal-Token`
(centralized in `packages/auth-client-py` — `make_verify_internal_request`),
plus a forwarded user bearer for `admin-api -> platform-api`. Durable
target: workload / managed identity — one change point, that helper.
`X-Internal-Caller` is emitted on every internal call for audit/log only.
