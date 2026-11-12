# DijiOne — Azure subscription strategy

Status and guardrails for where DijiOne DEV / UAT / PROD are hosted. Companion:
`docs/platform/deployment-topology.md`, `deploy/README.md`.

## Status (verified 2026-09-06, read-only)

`az account list` shows **one** subscription:

| Name | Id | State |
|---|---|---|
| **Dijital Team IT Production** | `7d97cf51-ba0a-4dca-ace4-9d0be5792ace` | Enabled |

Tenant `2abce006-6ea2-4675-b39d-33e0a54c46c7`. **No non-production
subscription exists or is available.** A new Azure subscription is **not**
created by DijiOne's Phase-1 work.

## Recommendation

| Environment | Target subscription |
|---|---|
| DEV + UAT | a dedicated **non-production** subscription |
| PROD | its **own production** subscription |

`main.bicep` / `foundation.bicep` are subscription-agnostic — moving an
environment to another subscription is a deployment target change, not an
architecture change.

## Interim (until a non-prod subscription exists)

DEV may run in **"Dijital Team IT Production"** with **every** guardrail below.
PROD still targets its own production subscription boundary and is **not**
provisioned in this subscription.

- `rg-dijione-dev` + `rg-dijione-shared` only — nothing goes into an existing
  resource group.
- Every resource carries `platform=dijione` + `env=dev` tags (Bicep `tags`).
- **RG-scoped RBAC** for anyone operating DEV — no subscription-level role
  grants.
- Isolated `kv-dijione-dev`; isolated `psql-dijione-dev` with its own admin
  credential.
- A **monthly budget + alert** on `rg-dijione-dev` (80% actual, 100%
  forecast) — created as a Phase-1 step, target ~$30/mo (Amendment 8).
- **No production provider secrets** in `kv-dijione-dev` — Lever, BambooHR and
  Graph stay mocked in DEV (`INTEGRATIONS_MODE=mock`, `EMAIL_SENDING_MODE=mock`).
- **No production database or production Key Vault access** from any DEV
  identity — separate RG, separate VNet, no peering.

## Registries

| Registry | Resource group | Environments |
|---|---|---|
| `crdijionenonprod` | `rg-dijione-shared` (non-prod subscription, or interim same subscription) | DEV + UAT |
| `crdijioneprod` | `rg-dijione-prod` (production subscription) | PROD |

The exact image **digest** validated in UAT is imported into `crdijioneprod`
with `az acr import` and verified before PROD deploys it — the production image
is never rebuilt. See `docs/platform/release-pipeline.md`.
