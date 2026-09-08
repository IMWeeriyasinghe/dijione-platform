# Hosted DEV — Phase 4 activation runbook

> **Status: ACTIVE (2026-09-08).** All three integrations are live in
> `rg-dijione-dev`: `AUTH_MODE=entra`, `recruitmentIntegrationsMode=live`
> (Lever), `peopleIntegrationsMode=live` (BambooHR). The Key Vault secrets
> `entra-client-secret-dev` / `lever-api-key-dev` / `bamboohr-api-key-dev`
> exist. Deployed images: `platform-api@sha256:fd8621ad…` (`8ba0613`),
> `recruitment-api@sha256:51c933eb…` (`b1ac89f`); the rest are the Phase 3
> digests. The section-2 commands below are kept for reproducibility /
> a UAT rebuild; sections 4–6 are the current verification + rollback.

Real internal Microsoft Entra authentication + controlled read-only Lever /
BambooHR integrations for the hosted Azure DEV environment
(`rg-dijione-dev`). This describes the **actual wired state** after the
Phase 4 IaC change.

Companion docs: `authentication.md` (the Entra OIDC design),
`bamboohr-live-discovery.md` (the BambooHR field survey),
`integrations/lever.md` (the Lever read-only contract),
`deployment-topology.md`.

---

## 1. What is already in place (no credential needed)

### Entra app registration — `dijione-dev`

Created in tenant `2abce006-6ea2-4675-b39d-33e0a54c46c7`:

| Property | Value |
|---|---|
| Display name | `dijione-dev` |
| Application (client) id | `2ea7f6b8-d3c2-4dda-b806-32549efeadb6` |
| Object id | `8931e5e3-57a8-460e-8fc3-d9c5b7cb5151` |
| Service principal (enterprise app) id | `3801cab3-a187-4336-8d66-26ce2ac4a669` |
| Sign-in audience | `AzureADMyOrg` (single tenant) |
| Web redirect URI | `https://shell-web.livelypebble-890e141a.southeastasia.azurecontainerapps.io/api/auth/callback` |
| Front-channel logout URL | `https://shell-web.livelypebble-890e141a.southeastasia.azurecontainerapps.io/logout` |
| Home-page URL | `https://shell-web.livelypebble-890e141a.southeastasia.azurecontainerapps.io` |
| id_token optional claims | `email`, `upn` |
| Delegated Microsoft Graph scopes | `openid`, `profile`, `email`, `User.Read` |
| id/access token implicit issuance | disabled (Authorization Code + PKCE only) |

Redirect URIs are **DEV only** — no UAT/PROD reply URLs are registered on
this app. UAT and PROD get their own `dijione-uat` / `dijione-prod`
registrations.

### Bicep wiring (`deploy/bicep/main.bicep`, `main.dev.bicepparam`)

`platform-api` env is now `AUTH_MODE`-driven:

- `authMode = 'entra'` (dev param) → platform-api receives `AUTH_MODE=entra`,
  `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_REDIRECT_URI`
  (`<publicBaseUrl>/api/auth/callback`), `PUBLIC_BASE_URL`, and
  `ENTRA_CLIENT_SECRET` from the `entra-client-secret-dev` Key Vault secret.
  The passwordless persona switcher is off (`dev_auth_enabled` is
  `false` when `auth_mode != 'dev'`), so `platform-api` `/api/auth/dev-*`
  returns 404.
- `authMode = 'dev'` → the previous behaviour (persona switcher, no
  ENTRA_* vars). This is the one-line rollback.
- `shell-web` always receives `PUBLIC_BASE_URL`.

Per-service `INTEGRATIONS_MODE` (was one platform-wide `mock`):

- `recruitmentIntegrationsMode` (default `mock`) → `recruitment-api`.
  `'live'` also attaches `lever-api-key-dev` as `LEVER_API_KEY`.
- `peopleIntegrationsMode` (default `mock`) → `people-api`. `'live'` also
  attaches `bamboohr-api-key-dev` as `BAMBOOHR_API_KEY`, and
  `bamboohrSubdomain` as `BAMBOOHR_SUBDOMAIN`.
- every other API is pinned to `mock`.
- `EMAIL_SENDING_MODE=mock` stays platform-wide.

With the dev param file at its committed values (`authMode='entra'`,
both provider modes `'mock'`) a deploy is **inert for the providers** and
only flips identity — and even that needs the Key Vault secret below.

---

## 2. PENDING CREDENTIAL — three drop-ins

### 2a. Entra client secret → `entra-client-secret-dev`

Requires **Key Vault Secrets Officer** (or Administrator) on
`kv-dijione-dev` for whoever runs it — the deploy service account
(`sa-paymentslip@dijitalteam.com`, objectId
`c2d2155f-5573-4b50-ba98-0da8e2032dca`) currently has **no** data-plane
role on that vault.

```bash
# one-time role grant (RG-scoped, DEV vault only)
az role assignment create \
  --assignee c2d2155f-5573-4b50-ba98-0da8e2032dca \
  --role "Key Vault Secrets Officer" \
  --scope /subscriptions/7d97cf51-ba0a-4dca-ace4-9d0be5792ace/resourceGroups/rg-dijione-dev/providers/Microsoft.KeyVault/vaults/kv-dijione-dev

# mint a client secret for the app and store it — value never printed
SECRET=$(az ad app credential reset --id 2ea7f6b8-d3c2-4dda-b806-32549efeadb6 \
           --display-name dev --years 1 --query password -o tsv)
az keyvault secret set --vault-name kv-dijione-dev \
  --name entra-client-secret-dev --value "$SECRET" -o none
SECRET=   # clear
```

### 2b. Lever DEV API key → `lever-api-key-dev`

A real Lever API token scoped for read discovery (CLAUDE.md §60 — the
live client is GET-only by construction; it uses the key only as the
Basic-auth username).

```bash
az keyvault secret set --vault-name kv-dijione-dev \
  --name lever-api-key-dev --value "<LEVER_DEV_API_KEY>" -o none
```

Then set `param recruitmentIntegrationsMode = 'live'` in
`main.dev.bicepparam`.

### 2c. BambooHR DEV API key → `bamboohr-api-key-dev` (+ subdomain)

```bash
az keyvault secret set --vault-name kv-dijione-dev \
  --name bamboohr-api-key-dev --value "<BAMBOOHR_DEV_API_KEY>" -o none
```

Then set `param peopleIntegrationsMode = 'live'` and
`param bamboohrSubdomain = '<company-subdomain>'` in `main.dev.bicepparam`.
The live client issues only `POST /v1/reports/custom?format=JSON` (BambooHR's
report-**read** API — no write endpoints; tenant-verified 2026-08-14).

---

## 3. Deploy

No image rebuild — every code path (platform-api Entra OIDC, shell-web
`/login` + `/api/auth/callback`, the Lever/BambooHR live clients) already
ships in the Phase 3 digests.

```bash
az deployment group create -g rg-dijione-dev -n dijione-workloads-phase4 \
  -f deploy/bicep/main.bicep -p deploy/bicep/main.dev.bicepparam \
  -p imageDigests=@<phase-3 digest map>
```

Artifact map is unchanged from Phase 3 (`docs` / the Phase 3 report):
6 API @ `2baa15d`, 6 web @ `fc1bac8`.

---

## 4. Verify

### Entra

1. `GET https://<shell-web>/api/auth/config` → `{"auth_mode":"entra"}`.
2. `GET https://<shell-web>/api/auth/dev-personas` → **404** (switcher off).
3. `GET https://<shell-web>/login` → 302 to
   `https://login.microsoftonline.com/2abce006-.../oauth2/v2.0/authorize?...`
   with `client_id=2ea7f6b8-...`, `redirect_uri=<shell-web>/api/auth/callback`,
   `code_challenge_method=S256`, `scope=openid profile email`.
4. **Interactive** (needs a human with a tenant account): complete the
   Microsoft sign-in. First login for a new identity → auto-created
   **inactive** → 403 "ask a platform administrator to activate it"
   (first-login policy C). A platform admin activates the user + assigns
   module access in the Admin Center; second login → lands authenticated
   on `/`.
5. APIs still reject a missing/garbage bearer token (401), and the
   DijiOne session token issued from Entra is the same HS256 contract
   every downstream service already consumes — no service change.
6. The external TalentFlow magic-link portal is unaffected — it never
   touches Entra.

### Lever (when live)

- `recruitment-sync-job` → `recruitment_sync_runs` row `SUCCEEDED`;
  postings / candidacies populated from the real tenant; re-run is
  idempotent (created→updated, no dupes); provider external IDs
  preserved; `PostingClientMapping` stays TalentFlow-owned and fails
  closed on any non-`DTC - <exact name>` tag.

### BambooHR (when live)

- `people-sync-job` → `people_sync_runs` row `SUCCEEDED`; `employees`
  populated (ACTIVE only); BambooHR id kept distinct from Employee
  Number; re-run idempotent. Birthday consumes People via `people-api`
  only — no BambooHR or `people_dev` access from `birthday-api`.

---

## 5. Rollback

- **Identity:** set `param authMode = 'dev'` → redeploy. Persona switcher
  returns; ENTRA_* vars drop. The `entra-client-secret-dev` secret and the
  app registration can stay (inert).
- **A provider:** set its `*IntegrationsMode` back to `'mock'` → redeploy.
  The live client is not constructed; the previous read model is
  retained (no wipe).
- Fast, no-redeploy identity rollback in an incident:
  `az containerapp update -g rg-dijione-dev -n platform-api --set-env-vars AUTH_MODE=dev`
  (a subsequent Bicep deploy re-asserts the param value).

---

## 6. Not in scope for Phase 4

HubSpot / `commercial-api` (stays a skeleton, not deployed). Real outbound
email (`EMAIL_SENDING_MODE` stays `mock`). UAT / PROD Entra registrations
and deployment. Lever writes (impossible by construction — do not add).
