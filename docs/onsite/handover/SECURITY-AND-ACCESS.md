# Security and access

## Users and permissions (DijiOne)
- Sign-in: Microsoft Entra ID via platform-api (DijiOne SSO); platform-api issues the DijiOne JWT.
- Module access: JWT `module_roles.onsite.{role, permissions}` — direct user grants plus active access-group
  grants (`AuthorizationService.effective_module_roles`). Assigned in Admin Center (admin-web).
- Roles: `ONSITE_VIEWER` = `onsite.dashboard.read`, `onsite.attendance.read`, `onsite.exceptions.read`;
  `ONSITE_ADMIN` = viewer + `onsite.health.read`, `onsite.identity.read`, `onsite.sync.request`, `onsite.sites.manage`.
- onsite-api checks permissions on every route (UI gating via `/api/onsite/me` is convenience only).
- Site scope: only sites enabled in `site_settings` are visible (fail closed); per-user site restriction is not
  implemented (planned option: `module_roles.onsite.site_ids`).
- Site enable/disable is an audited admin action (platform-api audit log). Do not flip it in the database.

## Service identities
| Identity | Access |
|---|---|
| onsite-api system-assigned MI per env | Azure SQL contained user `onsite-api-dijione-<env>`: SELECT on `onsite.AttendanceEvents`, `onsite.AgentStatus`, `onsite.Sites` (columns excluding `ApiKeyHash`). Script: `docs/onsite/sql-principal.sql` / Agent repo `grant-dijione-reader.ps1` |
| `app-diji-onsite-attendance` system MI | the only writer of the authoritative DB |
| `id-dijione-<env>` UAMI | AcrPull + Key Vault secrets for Container Apps; not used for SQL |
| Internal token (`internal-service-secret` in each env KV) | service-to-service calls (sync job → onsite-api, onsite-api → people-api) |
| Agent site key | per site; hash in `onsite.Sites.ApiKeyHash`, plain in KV `site-key-…` and DPAPI-protected on the PC |
| `diji_onsite_reader` (ZKBioTime) | SELECT-only Postgres role; session forced read-only with short timeouts |

## Secrets
- All runtime secrets are Key Vault references (`kv-dijione-<env>`, `kv-diji-onsite-attend`); no SQL passwords
  anywhere for Azure SQL (managed identity tokens only).
- Production Agent secrets exist only DPAPI-protected on `DESKTOP-V3H5OFI`; they cannot be decrypted elsewhere.
- Never copy `.env`, `agent.json`, `admin.token`, `.local/`, KV values, exports or databases between machines.
- Dev-only credentials in the Agent repo (`tests/DijiOnsiteAgent.IntegrationTests/PipelineFixture.cs`,
  `dev/`) belong to the local replica only.
- Repository scan 2026-11-13: no tracked CSV/XLSX/DB/key/cert files, no secret patterns, no DPAPI blobs in
  either repo. DijiOne CI runs gitleaks (`.github/workflows/secret-scan.yml`).

## Data protection
- No biometric templates are read or stored anywhere. Personnel exports contain personal data: keep off-repo,
  share minimally, delete after use. `.gitignore` in the Agent repo blocks `*.csv`.
- Photos are served only through authenticated proxies (people-api internal token → onsite-api permission check),
  `Cache-Control: private`; the BambooHR URL is never exposed.

## How the Mac agent gets access (approved mechanisms only)
- GitHub: the user's own GitHub auth on the Mac (`gh auth login` or SSH key) for both private repos.
- Azure: `az login` as the user on the Mac (same tenant), read-only commands unless approved.
- Azure SQL authoritative DB: Entra auth (`go-sqlcmd --authentication-method ActiveDirectoryAzCli`) **and** a
  firewall rule for the Mac's public IP — adding one changes production networking, so ask first.
- DijiOne UI: sign in with Entra at the environment URLs.
- Nothing is transferred from the Windows PC.

## Production controls
- PROD deployments only after DEV + UAT validation and explicit user approval; identical digests promoted
  (`az acr import` into `crdijioneprod`).
- In-container data reads in PROD are disallowed for agents by policy; use the UI or ask the user.
