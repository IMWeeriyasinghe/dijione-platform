# DijiOne — release pipeline (DEV → UAT → PROD)

The locked lifecycle. One reusable Bicep architecture; **build the application
artifact once and promote the exact immutable digest** — environment-specific
differences live only in Bicep parameters, Key Vault secrets, runtime env vars,
domains and identity/provider config, **never** in a rebuilt binary.

CD host (GitHub Actions vs Azure DevOps) is not yet chosen; `deploy/deploy.sh`
and `deploy/promote.sh` are the interim operator runbooks and express the same
lifecycle.

## Lifecycle

```
PR  ──►  CI (lint / test / build matrix)  ──►  Engineering Gatekeeper  ──►  merge to main
  │
  ├─ change detection (dorny/paths-filter — same filter set as PR #71)
  ├─ build ONLY affected images, ONCE, into crdijionenonprod  as  dijione/<svc>:<gitsha>
  ├─ record each image's immutable  sha256:<digest>
  │
  ├─ DEPLOY DEV        foundation.dev  →  init-secrets.sh dev  →  main.dev  -p imageDigests=<recorded>
  ├─ DEV migrations    migrate-<svc> jobs (own image, own DB), platform-api first
  ├─ DEV smoke / integration
  │
  ├─ ►► MANUAL DEV → UAT APPROVAL ◄◄
  │
  ├─ PROMOTE UAT       deploy/promote.sh dev uat <gitsha>
  │                    same registry, SAME digests — nothing is copied
  ├─ UAT migrations  →  UAT acceptance
  │
  ├─ ►► MANUAL UAT → PROD RELEASE APPROVAL ◄◄   (includes: migrations reviewed)
  │
  ├─ PROMOTE PROD      deploy/promote.sh uat prod <gitsha>
  │                    az acr import each digest crdijionenonprod → crdijioneprod
  │                    VERIFY imported digest == source digest  (fails hard on mismatch)
  ├─ PROD migrations  →  controlled revision rollout  →  PROD smoke
  └─ release complete
```

## What is environment-specific (and where it lives)

| Concern | Mechanism |
|---|---|
| Region, SKUs, replica floors/ceilings, storage, retention, HA, VNet CIDRs | `foundation.<env>.bicepparam` + `main.<env>.bicepparam` |
| Registry + its resource group | `main.<env>.bicepparam` (`imageRegistry*`) |
| Trust anchors, DB URLs, provider keys | `kv-dijione-<env>` (values written by `init-secrets.sh` / the pipeline secret step) |
| Internal service URLs, `AUTH_MODE`, `INTEGRATIONS_MODE` | `az containerapp update --set-env-vars` (deploy.sh step 5) |
| Custom domains, Entra app registration | per-env, out of band |

**Never** environment-specific: the application image. DEV, UAT and PROD run the
byte-identical container, addressed by the same `sha256:` digest.

## Migration pipeline

Migration-execution ownership stays with the schema owner. `main.bicep` creates
one **`migrate-<svc>`** Job per DB-owning service, each on **that service's own
image**, running `python -m alembic upgrade head` against its own alembic tree
with only its own `DATABASE_URL`. Order: infra → DB reachable → migrate
(`platform-api` first) → API rollout → web rollout → smoke. Forward-only;
rollback of a bad migration is PostgreSQL point-in-time restore, not
`alembic downgrade` (two migrations are deliberately irreversible). Destructive
migrations are `HUMAN_REQUIRED` and do not flow to PROD without explicit
sign-off.

## Rollback

Redeploy the previous recorded digest (`main.<env>.bicepparam`
`imageDigests`) and, if a migration must be undone, PITR-restore the database to
just before the migrate job.
