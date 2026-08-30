# DijiOne — first Azure DEV deployment

Meeting-DEV target (Data Ownership Architecture v2 + Pre-DEV Execution Plan):

- **Azure Container Apps** (consumption / scale-to-zero) for all services
- **one Azure Database for PostgreSQL Flexible Server** (Burstable B1ms, stoppable)
- **shell-web** = external ingress + env-driven Next.js rewrites → internal services
- **infra-level Microsoft Entra gate** ("Easy Auth") on shell-web; `AUTH_MODE=dev`
  (Dev Identity Mode) inside for the first cut; full in-app Entra SSO is Wave 4b
- `INTEGRATIONS_MODE=mock` everywhere — no live Lever/HubSpot/BambooHR, no local
  `.db` uploaded, fresh seeded demo data only
- **not deployed:** `spark-api` (skeleton). `birthday-*` optional.

Nothing here runs during planning. These are the exact steps for whoever owns
the Azure subscription + Entra tenant.

---

## 0. Prerequisites (user)

- `az login` (Azure CLI ≥ 2.60), on a subscription with spend approved (~$20–35/mo
  running; ~$10 with PostgreSQL stopped between demos).
- Docker, to build the images (`deploy/build-push.sh`).
- An **Entra app registration** for DijiOne DEV — single-tenant, **Web** platform,
  delegated `openid profile email`, one **client secret**. Note the **Tenant ID**
  and **Application (client) ID**. The redirect URI is added in step 5 once the
  shell-web hostname exists.
- An image registry: GitHub Container Registry (free) or Azure Container Registry
  Basic (~$5/mo).

## 1. Verify the images build (before touching Azure)

```bash
# from the repo root
docker build -f deploy/Dockerfile.api --build-arg SERVICE=platform-api -t dijione/platform-api .
docker build -f deploy/Dockerfile.api --build-arg SERVICE=admin-api     -t dijione/admin-api .
docker build -f deploy/Dockerfile.api --build-arg SERVICE=talent-api    -t dijione/talent-api .
docker build -f deploy/Dockerfile.api --build-arg SERVICE=birthday-api  -t dijione/birthday-api .   # optional
docker build -f deploy/Dockerfile.web --build-arg APP=shell-web    -t dijione/shell-web .
docker build -f deploy/Dockerfile.web --build-arg APP=admin-web    -t dijione/admin-web .
docker build -f deploy/Dockerfile.web --build-arg APP=talent-web   -t dijione/talent-web .
docker build -f deploy/Dockerfile.web --build-arg APP=birthday-web -t dijione/birthday-web .        # optional
```

Then run the stack locally against a throwaway Postgres to catch SQLite-isms and
prove the env-driven wiring (`docker network` + `postgres:16` container; set
`DATABASE_URL=postgresql+psycopg://...`, `PLATFORM_API_URL`, `TALENT_API_URL`, ...
per service). Run `./scripts/bootstrap-dev.sh` inside a temporary api container,
then `GET /health/deep` on each service.

> **Known-untested:** these Dockerfiles have not been `docker build`-verified in
> this environment (no Docker available at authoring time). Expect to iterate on
> the Next.js `standalone` copy paths and the `psycopg` wheel install on first
> build.

## 2. Provision Azure

```bash
./deploy/provision.sh          # edit the variables at the top first
```

Creates: resource group, Log Analytics workspace, Container Apps environment,
PostgreSQL Flexible Server (B1ms) + `platform_dev` and `talent_dev` databases +
a firewall rule for Azure services, and the Container Apps (internal ingress for
the APIs + `admin-web`/`talent-web`, external ingress for `shell-web`).

## 3. Build & push images

```bash
./deploy/build-push.sh         # set REGISTRY at the top
```

## 4. Point the Container Apps at the pushed images + set env/secrets

`provision.sh` wires the env vars and secret *references*; set the secret
*values* directly in Azure (never in a file):

```bash
az containerapp secret set -g rg-dijione-dev -n platform-api \
  --secrets jwt-dev-secret=<high-entropy> internal-secret=<high-entropy> \
            db-url='postgresql+psycopg://dijione:<pw>@psql-dijione-dev.postgres.database.azure.com/platform_dev?sslmode=require'
# repeat the shared jwt-dev-secret / internal-secret for admin-api, talent-api, birthday-api
# talent-api / birthday-api get their own db-url (talent_dev) — birthday-api can stay SQLite-on-nothing only if NOT deployed
```

Required env per service (localhost defaults are in each `.env.example`):

| Service | Env |
|---|---|
| `platform-api` | `DATABASE_URL`, `JWT_DEV_SECRET`, `INTERNAL_SERVICE_SECRET`, `API_CORS_ORIGINS=https://<shell-host>`, `DEV_IDENTITY_MODE=true`, `TALENT_API_URL=http://talent-api` |
| `admin-api` | `PLATFORM_API_URL=http://platform-api`, `TALENT_API_URL=http://talent-api`, `INTERNAL_SERVICE_SECRET`, `API_CORS_ORIGINS=https://<shell-host>` |
| `talent-api` | `DATABASE_URL`, `JWT_DEV_SECRET`, `INTERNAL_SERVICE_SECRET`, `PLATFORM_API_URL=http://platform-api`, `INTEGRATIONS_MODE=mock`, `API_CORS_ORIGINS=https://<shell-host>` |
| `birthday-api` (opt) | `DATABASE_URL`, `JWT_DEV_SECRET`, `INTERNAL_SERVICE_SECRET`, `PLATFORM_API_URL=http://platform-api`, `INTEGRATIONS_MODE=mock`, `EMAIL_SENDING_MODE=mock` |
| `shell-web` | `ADMIN_WEB_URL=http://admin-web`, `TALENT_WEB_URL=http://talent-web`, `BIRTHDAY_WEB_URL=http://birthday-web`, `PLATFORM_API_URL=http://platform-api`, `ADMIN_API_URL=http://admin-api`, `TALENT_API_URL=http://talent-api`, `BIRTHDAY_API_URL=http://birthday-api`, `SPARK_API_URL=http://spark-api` |
| `admin-web` | `PLATFORM_API_URL=http://platform-api`, `ADMIN_API_URL=http://admin-api` |
| `talent-web` | `PLATFORM_API_URL=http://platform-api`, `TALENT_API_URL=http://talent-api` |
| `birthday-web` (opt) | `PLATFORM_API_URL=http://platform-api`, `BIRTHDAY_API_URL=http://birthday-api` |

`http://<app-name>` resolves via the Container Apps environment's internal DNS.

## 5. Bootstrap the database

```bash
az containerapp job create -g rg-dijione-dev -n bootstrap-dev \
  --environment cae-dijione-dev --image <registry>/dijione/platform-api:latest \
  --trigger-type Manual --replica-timeout 600 \
  --env-vars DATABASE_URL=secretref:db-url JWT_DEV_SECRET=secretref:jwt-dev-secret \
             INTERNAL_SERVICE_SECRET=secretref:internal-secret INTEGRATIONS_MODE=mock \
  --command "/bin/sh" --args "-c" "cd /app && ./scripts/bootstrap-dev.sh"
az containerapp job start -g rg-dijione-dev -n bootstrap-dev
```

(Or `az containerapp exec` into a running api container and run
`./scripts/bootstrap-dev.sh` once.)

## 6. Entra gate + HTTPS

- Note shell-web's URL: `az containerapp show -g rg-dijione-dev -n shell-web --query properties.configuration.ingress.fqdn -o tsv` → `https://<fqdn>`.
- Add `https://<fqdn>/api/auth/callback` as a redirect URI on the app registration
  (needed now for Easy Auth; also for Wave 4b in-app SSO).
- Enable Container Apps built-in auth on shell-web (Microsoft provider,
  `Require authentication`, single-tenant):

```bash
az containerapp auth microsoft update -g rg-dijione-dev -n shell-web \
  --client-id <app-client-id> --client-secret <app-client-secret> \
  --tenant-id <tenant-id> --yes
az containerapp auth update -g rg-dijione-dev -n shell-web \
  --unauthenticated-client-action RedirectToLoginPage --redirect-provider azureactivedirectory
```

Container Apps default hostnames get a **free managed TLS cert** — no DNS work
for the meeting DEV. A custom domain (`dev.dijione.<domain>`) is a later add.

## 7. Smoke test

```bash
for s in platform-api admin-api talent-api; do
  az containerapp exec -g rg-dijione-dev -n $s --command "curl -s localhost:8000/health/deep"; done
```

Then run the Playwright smoke suite (`e2e/`) against `https://<fqdn>` — see the
Pre-DEV Execution Plan §19.

## Teardown

```bash
az group delete -g rg-dijione-dev --yes --no-wait
```

## Cost control

Stop PostgreSQL between demos:

```bash
az postgres flexible-server stop  -g rg-dijione-dev -n psql-dijione-dev
az postgres flexible-server start -g rg-dijione-dev -n psql-dijione-dev
```

Container Apps scale to zero on their own when idle.

---

## Wave 4b — in-app Entra SSO (after the meeting)

Set on `platform-api`: `AUTH_MODE=entra`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`,
`ENTRA_CLIENT_SECRET` (secret), `ENTRA_REDIRECT_URI=https://<fqdn>/api/auth/callback`,
`PUBLIC_BASE_URL=https://<fqdn>`. Optionally drop the Easy Auth gate. Activate the
demo users in the Admin Center. Re-run smoke with the real login flow.
