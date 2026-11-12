# DijiOne — Azure deployment

**Provisioning of record: Bicep** (`deploy/bicep/`). `deploy/provision.sh` and
`deploy/build-push.sh` are **superseded** — kept for reference only.

> Nothing here runs during planning. These are the Phase 1+ steps for whoever
> owns the Azure subscription + Entra tenant. Every step is gated on explicit
> human approval — see `docs/platform/pre-cloud-handoff.md`.

Approved decisions: region **`southeastasia`**; **PostgreSQL Flexible Server**
(DijiOne standard, all environments); **private DB networking via VNet
integration** from DEV onward; **build once / promote the exact image digest**
DEV→UAT→PROD; first DEV = full platform incl. DijiBirthday; `commercial-api` /
`spark-api` not deployed; **lean cost baseline** — every service scale-to-zero in
DEV/UAT, only `platform-api` + `shell-web` pinned in PROD.

---

## Layout

```
deploy/
  bicep/
    foundation.bicep              network + Log Analytics + Key Vault (EMPTY) + PostgreSQL + ACA environment
    foundation.{dev,uat,prod}.bicepparam
    main.bicep                    Container Apps + Jobs only; deploy by sha256 digest; references cae/kv as existing
    main.{dev,uat,prod}.bicepparam
    modules/
      network.bicep              VNet + snet-aca(/23, ACA-delegated) + snet-postgres(/27, PG-delegated) + Private DNS zone
      observability.bicep        Log Analytics + retention + daily ingest cap
      acr.bicep                  Container Registry (Basic) — deployed once per registry
      keyvault.bicep             Key Vault (RBAC). NO secret values, not even placeholders.
      postgres.bicep             Flexible Server + databases[] + max_connections + public|private + HA mode
      containerapp-env.bicep     the workload-profiles ACA environment (Consumption profile, VNet-integrated)
      containerapp.bicep         ONE reusable Container App + its Key Vault Secrets User grant
      job.bicep                  ONE reusable Job (Schedule|Manual) + its Key Vault Secrets User grant
      acr-pull.bicep             AcrPull grant, deployed at the REGISTRY's resource group (may differ from the workload RG)
  deploy.sh                      operator runbook: foundation -> build once -> assert secrets -> workloads -> migrate -> smoke
  init-secrets.sh                writes the real Key Vault secret values between foundation and workloads
  promote.sh                     promote the exact digest dev->uat (same registry) / uat->prod (az acr import + verify)
  wake-dev.sh / park-dev.sh      cost park/unpark (start/stop PostgreSQL); also -uat wrappers
  Dockerfile.api / Dockerfile.web  one reusable image per kind, build-arg parameterised -> independent images
  provision.sh / build-push.sh   SUPERSEDED (reference only)
```

## Registries

| Registry | Resource group | Environments |
|---|---|---|
| `crdijionenonprod` | `rg-dijione-shared` | DEV + UAT (shared) |
| `crdijioneprod` | `rg-dijione-prod` | PROD (isolated) |

Create each once: `az deployment group create -g <rg> -f deploy/bicep/modules/acr.bicep -p name=<registry>`.

## Per-app version/build footer metadata

Every web image build passes `GIT_SHA` (and legacy `BUILD_DATE`, no longer
shown) build args so each app's footer can show its own version (from that
app's own `package.json`) and commit SHA — never a single shared
DijiOne-wide version. A third, genuinely optional footer line, `Released
<date>`, is sourced at **runtime** from a per-app `RELEASE_DATE` Container
App environment variable, set ad hoc via `az containerapp update
--set-env-vars RELEASE_DATE=<UTC timestamp>` in the same call that deploys
that app's new image (never as a separate revision, and never one value
written identically to every service). Full convention, including the
rule that major version bumps need explicit approval, and why
`RELEASE_DATE` must be read at request time rather than baked in at build
time: `docs/platform/versioning.md`.

**Follow-up work, not yet implemented — `main.bicep` does not currently
know about `RELEASE_DATE` at all.** Because Bicep's `env` array on a
Container App resource is fully **replaced**, not merged, on every
deployment, running `main.bicep` against a service that has an ad hoc
`RELEASE_DATE` set (as above) will **silently wipe it**, with no error. Do
not add a `releaseDates` (or similarly named) bicep parameter to fix this
without, in the same change, also giving `deploy.sh`/`deploy/deploy.sh`
logic that (1) reads every currently-deployed service's live `RELEASE_DATE`
before the run, (2) carries each one forward into the parameter unless that
service is itself being released this run, and (3) only then invokes
`main.bicep`. A bicep parameter with an empty/default value and no such
wrapper logic is **not safe** — it looks like a real mechanism but silently
erases every other app's release date the next time someone runs a routine
`main.bicep` deployment. Until this follow-up lands: **do not run a full
multi-service `main.bicep` deployment against an environment that has any
app-specific `RELEASE_DATE` set without first manually capturing
(`az containerapp show ... --query "properties.template.containers[0].env"`)
and understanding what would be lost.**

**Second follow-up, same shape of gap — web apps have no `APP_ENV`.**
`main.bicep`'s `commonApiEnv` (which sets `APP_ENV`) is only applied when
`s.kind == 'api'`; no equivalent exists for `kind == 'web'`, so no web app
(`birthday-web` included) receives `APP_ENV` from Bicep at all. This
mattered starting with DijiBirthday's Email Safety feature
(`docs/birthday/email-safety.md`), whose non-production-only nav item reads
`APP_ENV` via `birthday-web`'s own `/api/meta` route. Until `main.bicep`
gets a `commonWebEnv`-style addition, `APP_ENV` is set ad hoc on
`birthday-web` (`az containerapp update --set-env-vars APP_ENV=development`
in DEV) — same "silently wiped by a full `main.bicep` run" risk as
`RELEASE_DATE` above, and the same rule applies: capture it first before a
full redeploy of a web app in an environment where it's been set ad hoc.

## Prerequisites (user)

- `az login` on a subscription with spend approved (see
  `docs/platform/azure-subscriptions.md` — only "Dijital Team IT Production"
  exists today; DEV runs there with guardrails, PROD keeps its own boundary).
- `rg-dijione-<env>` and `rg-dijione-shared` created
  (`az group create -n rg-dijione-dev -l southeastasia --tags platform=dijione env=dev`).
- Providers registered: `Microsoft.App`, `Microsoft.DBforPostgreSQL`
  (`Microsoft.Network` already is).
- **No local Docker needed** — images build server-side with `az acr build`.
- An Entra app registration for DijiOne DEV — single-tenant, **Web**, delegated
  `openid profile email`, one client secret. Redirect URI added after `shell-web`
  exists.

## Deploy (one environment)

```bash
# 1. foundation + build + secrets + workloads + migrate + smoke, in order
./deploy/init-secrets.sh dev          # run once foundation exists (deploy.sh runs foundation first)
./deploy/deploy.sh dev <gitsha>
```

`deploy.sh dev <gitsha>` runs: unpark PostgreSQL → **foundation** deployment →
**build each image once** into `crdijionenonprod` as `:<gitsha>` and record its
`sha256:` digest → **assert** every expected Key Vault secret has a real value
(fails loudly, pointing at `init-secrets.sh`) → **workloads** deployment
(`main.dev.bicepparam` `-p imageDigests=<recorded>`) → per-service env
(`az containerapp update` for the internal `http://<name>` URLs) → **run the
per-service `migrate` jobs** → `GET /health/deep` on each backend → print the
three public FQDNs **and the recorded digests**.

`init-secrets.sh dev` generates the 3 trust anchors (only if absent) and writes
one `database-url-<domain>` per DB-owning service from the resolved PostgreSQL
FQDN + the admin password you enter. A secret value is never echoed, never
written to disk, never passed on a command line.

## Promote (never rebuild)

```bash
./deploy/promote.sh dev uat <gitsha>    # same registry, same digests — deploy main.uat
# ...UAT acceptance + MANUAL approval...
./deploy/promote.sh uat prod <gitsha>   # az acr import each digest -> crdijioneprod, verify, deploy main.prod
```

The digests promoted are read from the upstream `dijione-workloads-<gitsha>`
deployment, so what ships downstream is provably the artifact that passed
upstream. Full lifecycle: `docs/platform/release-pipeline.md`.

## PostgreSQL networking — private (VNet integration), all environments

`foundation.bicep` creates, per environment: `vnet-dijione-<env>` (`/21`, no
peering), `snet-aca` (`/23`, delegated `Microsoft.App/environments`),
`snet-postgres` (`/27`, delegated
`Microsoft.DBforPostgreSQL/flexibleServers`), and a Private DNS zone
`psql-dijione-<env>.private.postgres.database.azure.com` linked to the VNet.
The Flexible Server is created with `publicNetworkAccess = Disabled` — **no
public endpoint**. This is *Private access / VNet integration*, **not** Private
Link / Private Endpoint (there is no `privatelink.*` zone and no
`privateEndpoints` resource). The ACA environment is a **workload-profiles**
environment (Consumption profile only — no fixed fee) placed on `snet-aca`; its
VNet is create-time and cannot be toggled later.

`pgNetworkMode = 'public'` remains in `postgres.bicep` as a documented escape
hatch only; every `.bicepparam` uses `'private'`.

## Key Vault bootstrap

Bicep declares the vault, its RBAC, and the expected secret **names**
(`output expectedSecretNames`). It never creates a secret **value** — not even a
placeholder. Order: **foundation** (vault empty) → **`init-secrets.sh`** (real
values) → **workloads** (`main.bicep`; Container App `keyVaultUrl` references now
resolve; a missing secret fails the deploy, which is correct).

## Migration jobs

Migration-execution ownership stays with the schema owner. `main.bicep` creates
one `migrate-<svc>` Job per DB-owning service, each on **that service's own
image**, running `python -m alembic upgrade head` against its own alembic tree
with only its own `DATABASE_URL`. `deploy.sh` / `promote.sh` start them in order
(`platform-api` first). There is no single image that "knows" every service's
migrations.

## Cost control (Amendment 8)

- Every Container App is `minReplicas=0` in DEV/UAT (`main.{dev,uat}.bicepparam`);
  only `platform-api` + `shell-web` are pinned in PROD. Idle Container Apps cost
  $0.
- `./deploy/park-dev.sh` stops `psql-dijione-dev` (storage-only billing, ~$4–5/mo);
  `./deploy/wake-dev.sh` (with `WARM=1` to pre-warm) resumes it. Same for
  `-uat`. A stopped Flexible Server auto-resumes after 7 days — re-run `park` to
  keep it parked.
- DEV target ≈ $20–27/mo running, ≈ $12–16 mostly-parked. Set a budget + alert
  on `rg-dijione-dev`.

## Entra gate + HTTPS

DEV uses the free `*.<region>.azurecontainerapps.io` hostnames (free managed
TLS, no DNS work). After `shell-web` exists:

```bash
FQDN=$(az containerapp show -g rg-dijione-dev -n shell-web --query properties.configuration.ingress.fqdn -o tsv)
# add https://$FQDN/api/auth/callback as a redirect URI on the app registration, then:
az containerapp auth microsoft update -g rg-dijione-dev -n shell-web \
  --client-id <app-client-id> --client-secret <app-client-secret> --tenant-id <tenant-id> --yes
az containerapp auth update -g rg-dijione-dev -n shell-web \
  --unauthenticated-client-action RedirectToLoginPage --redirect-provider azureactivedirectory
```

The two external portals (`talentflow-portal-web`, `birthday-supplier-web`) get
their **own** FQDNs and are **not** gated by Easy Auth — their own magic-link /
supplier-token flow is the gate.

## Data — MIGRATE / IDENTITY / never-business

`deploy.sh` runs `migrate-<svc>` jobs (schema + catalog/reference only,
including the platform-owned 28-client canonical master set — Option A, final).
It does **not** seed business data. Optionally, for a demoable DEV:

```bash
az containerapp exec -g rg-dijione-dev -n platform-api --command "python scripts/seed.py --identity-only"
```

Full detail: `docs/platform/hosted-dev-data.md`.

## Teardown

```bash
az postgres flexible-server stop -g rg-dijione-dev -n psql-dijione-dev   # storage-only
az group delete -g rg-dijione-dev --yes --no-wait                        # full teardown
```

## DijiBirthday outbound email (Managed Identity, packages/mail-client-py)

Full design, the Exchange RBAC runbook, and the future-app-adoption
checklist: `docs/platform/email-architecture.md`.

**Follow-up work, not built yet — tracked here on purpose.**
`MAIL_TRANSPORT`/`MAIL_POLICY`/`MAIL_SHARED_MAILBOX`/`MAIL_ALLOWLIST` are
currently only set ad hoc on birthday-api's DEV Container App
(`az containerapp update --set-env-vars ...`) for controlled real-Graph
testing — they are **not yet** parameterized in `main.bicep`, which still
declares no email-related env vars for birthday-api at all. **Do not run a
full `main.bicep` deployment against an environment that has any of these
ad hoc env vars set** without first manually capturing
(`az containerapp show ... --query "properties.template.containers[0].env"`)
and understanding what would be lost — Container Apps `env` arrays are
fully replaced, not merged, by a bicep deployment (the same lesson already
documented for `RELEASE_DATE` in `docs/platform/versioning.md`). When this
is eventually built: a `mailTransport`/`mailPolicy`/`mailSharedMailbox`/
`mailAllowlist` set of bicep parameters, plus a deployment-wrapper
preserve-then-override mechanism — never the parameters alone.

## Wave 4b — in-app Entra SSO (after the first DEV works)

Set on `platform-api`: `AUTH_MODE=entra`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`,
`ENTRA_CLIENT_SECRET` (Key Vault),
`ENTRA_REDIRECT_URI=https://<fqdn>/api/auth/callback`,
`PUBLIC_BASE_URL=https://<fqdn>`. Optionally drop the Easy Auth gate.
`docs/platform/authentication.md` has the full flow.
