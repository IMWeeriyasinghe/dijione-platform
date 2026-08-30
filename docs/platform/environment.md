# Environment & secrets contract

Single reference for how configuration and secrets are handled across DijiOne.
Setup steps live in [`local-development.md`](local-development.md); this page is
the *contract* — what may be committed, what may not, and why.

## Model

- **Each backend service is configured independently.** There is no shared
  `.env`. Every service reads its own `apps/<service>/.env` via
  `pydantic-settings` (`app/core/config.py`), and a real OS environment variable
  always overrides the file.
- **The 5 web apps have no environment files.** They call same-origin relative
  paths, proxied by each app's `next.config.ts` `rewrites()`. Never introduce a
  `NEXT_PUBLIC_*` secret — those are shipped to the browser.
- **`apps/<service>/.env.example` is the committed source of truth for shape.**
  It lists every key with a safe placeholder / empty value. `apps/<service>/.env`
  (the real file) is git-ignored and never committed.
- **Staging / production inject via host environment variables**, not files —
  e.g. Azure App Service application settings sourced from Key Vault. Because
  `pydantic-settings` reads OS env over the file, no code change is needed and no
  `.env.production` / `.env.staging` file ever enters the repo.

## Services and their configuration

| Service | Port | DB | Real-secret keys (only ever in `.env`) | Notes |
|---|---|---|---|---|
| `platform-api` | 8000 | SQLite | `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET` | Owns identity, authz, module registry, audit, notifications |
| `admin-api` | 8001 | none | — | Stateless gateway; forwards to platform-api + talent-api |
| `talent-api` | 8002 | SQLite | `LEVER_API_KEY`, `LEVER_WEBHOOK_SIGNING_SECRET`, `HUBSPOT_ACCESS_TOKEN`, `AZURE_STORAGE_CONNECTION_STRING` | `INTEGRATIONS_MODE=mock` locally; Lever is **read-only** (CLAUDE.md §60) |
| `birthday-api` | 8003 | SQLite | `BAMBOOHR_API_KEY`, `BAMBOOHR_SUBDOMAIN`, `GRAPH_*` | `INTEGRATIONS_MODE` and `EMAIL_SENDING_MODE` are independent; both default `mock` |
| `spark-api` | 8004 | none | — | Skeleton |

## Shared trust anchors (committed placeholders, must be overridden in real deploys)

Present in every backend `.env.example` and as defaults in `config.py`:

| Key | Placeholder | Rule |
|---|---|---|
| `JWT_DEV_SECRET` | `dev-only-insecure-secret-change-me` | **Identical** across every backend — services verify tokens locally from claims |
| `INTERNAL_SERVICE_SECRET` | `dev-only-internal-secret-change-me` | **Identical** across every backend — service-to-service trust |

In any deployed environment both must be replaced with real, high-entropy values
delivered through the host's secret store.

## Integration mode switches

| Var | Services | Values | Default |
|---|---|---|---|
| `INTEGRATIONS_MODE` | talent-api, birthday-api | `mock` \| `live` | `mock` |
| `EMAIL_SENDING_MODE` | birthday-api | `mock` \| `live` | `mock` |

`live` requires the corresponding real credentials to be set or the client raises
a `*NotConfiguredError`. CI forces both to `mock` so no test can reach an
external system.

## The rule for changing configuration

Any field added to a service's `app/core/config.py` `Settings` class **must** be
mirrored — with a safe placeholder or empty value — in that service's
`.env.example`, **in the same pull request**. The PR template has a checkbox for
this.

## Enforcement (three layers)

1. **`.gitignore`** — `.env` and `.env.*` are ignored except `*.env.example`;
   plus `*.pem`, `*.key`, `*.pfx`, `*.p12`, `*.keystore`, `serviceAccount*.json`,
   `**/secrets.json`.
2. **Local `gitleaks` pre-commit hook** — `.pre-commit-config.yaml`; run
   `pip install pre-commit && pre-commit install` once.
3. **`secret-scan` GitHub Actions workflow** — gitleaks on every push and PR.

If a secret is ever committed, follow the runbook in
[`../../SECURITY.md`](../../SECURITY.md): rotate first, then purge history.

## Local databases

`apps/*/*.db` (and `test_*.db`) are git-ignored. With `INTEGRATIONS_MODE=live`
they may hold read copies of real Lever / BambooHR data — never `git add -f`
them.
