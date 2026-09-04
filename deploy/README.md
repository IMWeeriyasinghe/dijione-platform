# DijiOne — Azure DEV deployment

**Provisioning of record: Bicep** (`deploy/bicep/`), driven by
`deploy/deploy.sh`. `deploy/provision.sh` and `deploy/build-push.sh` are
**superseded** — kept only for reference until the Bicep path is verified
against a real subscription.

> Nothing in this directory runs during planning. These are the steps for
> whoever owns the Azure subscription + Entra tenant. Every step is gated
> on explicit human approval — see `docs/platform/pre-cloud-handoff.md`.

Approved decisions (planning session): **region `southeastasia`**; short
Container App names kept as the internal DNS identifiers; `talent-api`
`min-replicas=1` for DEV; **Key Vault from day one**; Easy Auth on
`shell-web` as the interim perimeter gate (not the final identity design);
first DEV = **full platform incl. DijiBirthday**; `commercial-api` /
`spark-api` not deployed.

---

## Layout

```
deploy/
  bicep/
    main.bicep                    orchestrator (RG scope); loops the service catalogue
    main.dev.bicepparam           DEV params (imageTag + pgAdminPassword supplied at deploy time)
    modules/
      observability.bicep         Log Analytics + daily cap
      acr.bicep                   Container Registry (Basic)
      keyvault.bicep              Key Vault (RBAC) + placeholder secret versions
      postgres.bicep              Flexible Server B1ms + databases[] + PgBouncer + public|private networking
      containerapp-env.bicep      the single Container Apps Environment
      containerapp.bicep          ONE reusable Container App (api|web) + its AcrPull / KV Secrets User grants
      job.bicep                   ONE reusable Job (Schedule|Manual) + its grants
  deploy.sh                       operator runbook: az acr build -> az deployment -> migrate jobs -> smoke
  Dockerfile.api / Dockerfile.web shared, build-arg parameterised images
  provision.sh / build-push.sh    SUPERSEDED (reference only)
```

## Prerequisites (user)

- `az login` (Azure CLI ≥ 2.60) on a subscription with spend approved.
- Resource group `rg-dijione-dev` created (`az group create -n rg-dijione-dev -l southeastasia`).
- **No local Docker needed** — images build server-side with `az acr build`.
- An Entra app registration for DijiOne DEV — single-tenant, **Web**, delegated
  `openid profile email`, one client secret. Redirect URI added in step 5.

## Deploy

```bash
# 1. set the Key Vault secret VALUES (once; never in a file)
az keyvault secret set --vault-name kv-dijione-dev -n jwt-dev-secret            --value "$(openssl rand -hex 32)"
az keyvault secret set --vault-name kv-dijione-dev -n internal-service-secret   --value "$(openssl rand -hex 32)"
az keyvault secret set --vault-name kv-dijione-dev -n external-session-jwt-secret --value "$(openssl rand -hex 32)"
#    ...and one database-url-<domain> per DB-owning service, e.g.
az keyvault secret set --vault-name kv-dijione-dev -n database-url-platform \
  --value 'postgresql+psycopg://dijione:<pw>@psql-dijione-dev.postgres.database.azure.com/platform_dev?sslmode=require'

# 2. build + deploy + migrate + smoke — one command, one environment
./deploy/deploy.sh dev <gitsha>
```

`deploy.sh` runs: start PostgreSQL → `az acr build` each image as
`:<gitsha>` + `:dev` → check the KV secrets are set → `az deployment group
create` (Bicep) → per-service env (`az containerapp update --set-env-vars`
for the internal `http://<name>` URLs) → **run the per-service `migrate`
jobs** → `GET /health/deep` on each backend → print the three public FQDNs.

## 5. Entra gate + HTTPS

DEV uses the free `*.<region>.azurecontainerapps.io` hostnames (free
managed TLS, no DNS work). After `shell-web` exists:

```bash
FQDN=$(az containerapp show -g rg-dijione-dev -n shell-web --query properties.configuration.ingress.fqdn -o tsv)
# add https://$FQDN/api/auth/callback as a redirect URI on the app registration, then:
az containerapp auth microsoft update -g rg-dijione-dev -n shell-web \
  --client-id <app-client-id> --client-secret <app-client-secret> --tenant-id <tenant-id> --yes
az containerapp auth update -g rg-dijione-dev -n shell-web \
  --unauthenticated-client-action RedirectToLoginPage --redirect-provider azureactivedirectory
```

The two external portals (`talentflow-portal-web`, `birthday-supplier-web`)
get their **own** FQDNs and are **not** gated by Easy Auth — their own
magic-link / supplier-token flow is the gate.

## Data — MIGRATE / IDENTITY / never-business

`deploy.sh` runs `migrate-<svc>` jobs (schema + catalog/reference only).
It does **not** seed. Optionally, for a demoable DEV:

```bash
# staff dev personas + RBAC only — no clients, no business data
az containerapp job start -g rg-dijione-dev -n migrate-platform-api   # already run by deploy.sh
az containerapp exec -g rg-dijione-dev -n platform-api --command \
  "python scripts/seed.py --identity-only"
```

Full detail and the open "canonical Client master set" question:
`docs/platform/hosted-dev-data.md`.

## PostgreSQL networking comparison (Amendment 2)

`postgres.bicep` takes `networkMode`:

| | **A. `public`** (DEV default) | **B. `private`** (UAT/PROD target) |
|---|---|---|
| Extra Azure resources | none | a VNet + a subnet delegated to `Microsoft.DBforPostgreSQL/flexibleServers`, a Private DNS zone (`*.private.postgres.database.azure.com`), the ACA environment created **with** VNet integration (an `infrastructureSubnetId`), and a DNS-zone link |
| Monthly DEV cost delta | **$0** | VNet/subnet/Private DNS are free; the real cost is the ACA environment's **workload-profile / dedicated infra** requirement for VNet integration — a Consumption-only environment on the *default* (non-VNet) infra can't reach a VNet-only PG. Expect **+$0–?** on Consumption profiles where VNet is supported, or a workload-profile environment (~$0 idle, per-vCPU-hour when active) otherwise |
| ACA networking complexity | trivial | the environment must be created on a `/23`+ subnet up front (can't be added later); one more thing that can misconfigure |
| DNS requirements | none (public FQDN + `sslmode=require`) | the Private DNS zone must be linked to the environment's VNet or name resolution fails |
| UAT/PROD parity | **weaker** — DEV differs from prod on the one axis that matters for a DB | **strong** — identical shape |
| Operational overhead | `az postgres flexible-server stop/start` for cost; a `sslmode=require` firewall rule for "Azure services" | subnet/zone lifecycle; no public endpoint to fat-finger |
| Security | public endpoint (mitigated: `publicNetworkAccess=Enabled` + **only** an "Allow Azure services" rule — **no** `0.0.0.0–255.255.255.255`; TLS required; creds in Key Vault) | no public endpoint at all |

**Recommendation:** DEV stays **`public`** (materially simpler and free;
the exposure is minimised — TLS-required, Key-Vault creds, no broad
firewall rule). **UAT/PROD move to `private`** — the Bicep already takes
the params (`pgNetworkMode=private` + `pgDelegatedSubnetId` +
`pgPrivateDnsZoneId`); the remaining work is the VNet + delegated subnet +
Private DNS zone module and creating `cae-dijione-<env>` with VNet
integration. Tracked as a UAT prerequisite, not a DEV blocker. This is
**not** silently locking DijiOne to public PostgreSQL.

## Migration job design (Amendment 4)

Migration-execution ownership stays with the schema owner. `main.bicep`
creates **one `migrate-<svc>` Job per DB-owning service**, each on **that
service's own image**, running `python -m alembic upgrade head` against
that service's own alembic tree, with only its own `DATABASE_URL` secret.
`deploy.sh` starts them in order (`platform-api` first). There is no single
image that "knows" every service's migrations.

## Teardown / cost control

```bash
az postgres flexible-server stop  -g rg-dijione-dev -n psql-dijione-dev   # storage-only ~$4-6/mo
az group delete -g rg-dijione-dev --yes --no-wait                          # full teardown
```

## Wave 4b — in-app Entra SSO (after the first DEV works)

Set on `platform-api`: `AUTH_MODE=entra`, `ENTRA_TENANT_ID`,
`ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET` (Key Vault),
`ENTRA_REDIRECT_URI=https://<fqdn>/api/auth/callback`,
`PUBLIC_BASE_URL=https://<fqdn>`. Optionally drop the Easy Auth gate.
`docs/platform/authentication.md` has the full flow.
