# DijiAtWork — DEV deployment

**Status:** prepared, not deployed. `deployAtwork` is `false`. The module stays
`COMING_SOON` until its activation is separately approved.

## What is configured

| Item | Where |
|---|---|
| `atwork-api`, `atwork-web` (internal ingress only) | `deploy/bicep/main.bicep`, `deployAtwork` |
| `atwork_<env>` database, `database-url-atwork` secret | `foundation.bicep`, `init-secrets.sh` |
| Migrations | `migrate-atwork-api` job, `deploy.sh`, `promote.sh` |
| Scheduled alerts | `atwork-notifications-job`, every 15 minutes |
| Gateway build arguments | `deploy/Dockerfile.web` (`ATWORK_API_URL`, `ATWORK_WEB_URL`) |
| Gateway routes | `shell-web/next.config.ts`: `/atwork`, `/atwork/:path*`, `/api/atwork/:path*` |

## Environment

| Variable | Source |
|---|---|
| `APP_ENV`, `API_CORS_ORIGINS` | Common API settings |
| `DATABASE_URL` | Key Vault `database-url-atwork` |
| `PLATFORM_JWT_SECRET` | Key Vault `jwt-<env>-secret`, verified locally |
| `INTERNAL_SERVICE_SECRET` | Key Vault |
| `PLATFORM_API_URL` | `http://platform-api` |

Health: `GET /health` (liveness), `GET /health/deep` (database and migration head).

## Authentication and access

`atwork-api` has no Entra configuration of its own: it verifies Platform Core's
signed claims. DEV sign-in follows `authMode` on `platform-api`. Roles are assigned
in the Admin Center.

## DEV deployment commands (only after authorization)

Run from a clean checkout of the approved commit, signed in to Azure, with bash 4
or later (`deploy.sh` uses `mapfile`; the macOS system bash is too old).

1. Read the current state first. Stop if `platform_dev`'s `alembic_version` is not on
   the chain in "Platform Core migration integration".
2. In `foundation.dev.bicepparam` and `main.dev.bicepparam`, set `deployAtwork = true`
   as a reviewed change.
3. Create the database and the `database-url-atwork` secret:

   ```bash
   az deployment group create -g rg-dijione-dev -f deploy/bicep/foundation.bicep \
     -p deploy/bicep/foundation.dev.bicepparam
   DEPLOY_ONSITE=true DEPLOY_ATWORK=true deploy/init-secrets.sh dev
   ```

4. Deploy. `DEPLOY_ONSITE=true` is required because DEV runs Diji On-site, and
   `deploy.sh` rebuilds and redeploys every DEV application, not only DijiAtWork:

   ```bash
   DEPLOY_ONSITE=true DEPLOY_ATWORK=true deploy/deploy.sh dev "$(git rev-parse HEAD)"
   ```

5. Confirm the `migrate-platform-api` and `migrate-atwork-api` executions succeeded:

   ```bash
   az containerapp job execution list -g rg-dijione-dev -n migrate-atwork-api -o table
   ```

6. Run the smoke test as a restricted group. The module card stays static while
   `COMING_SOON`, so testers use `/atwork` directly.

## DEV-only activation (separate approval)

Follow `k1l2m3n4o5p6_activate_onsite_module_dev.py`: a new data migration that
sets only the `atwork` row to `ACTIVE`, only when `APP_ENV` is `development`. UAT and
Production keep `COMING_SOON`. Assign `ATWORK_USER` and, for the restricted test
group only, `ATWORK_MANAGER` in the Admin Center.

## DEV URLs

DijiAtWork uses the existing DijiOne DEV domain and shell gateway, like Diji On-site.
It has no DNS record, hostname, certificate or public endpoint of its own.

- Employee: <https://dijione-dev.dijitalteam.com/atwork>
- Management: <https://dijione-dev.dijitalteam.com/atwork/management>

`/api/atwork/internal/*` is blocked at the gateway and is reachable only inside the
Container Apps environment, with the internal service secret.

## DEV smoke test

- [ ] `/health/deep` on `atwork-api` reports the database OK and the migration up to date.
- [ ] Sign in at <https://dijione-dev.dijitalteam.com>; `/atwork` opens with no second sign-in.
- [ ] Signed out, open `/atwork/management` directly; after sign-in it returns there.
- [ ] `POST /api/atwork/internal/notifications/run` on the DEV domain returns 404.
- [ ] An `ATWORK_USER` is refused `/atwork/management`.
- [ ] Check in, break, end break, confirm check-out, check in again; totals add up.
- [ ] Submit a missing-session request. A reviewer gets a notification that opens it.
- [ ] The requester does not get the reviewer notification.
- [ ] Approve and reject another; the employee is notified, with the reason on rejection.
- [ ] Start `atwork-notifications-job` manually; it succeeds. A second run creates nothing new.
- [ ] Download CSV and Excel; check filename, time zone and Export Information.

## UAT and Production release

Targeted, in this order per environment. Nothing else is rebuilt or redeployed.
`shell-web` needs no change: UAT and PROD already run `0437a89`, which has the
`/atwork` routes. `admin-web` is deferred: the current build shows default access as
an unlabeled inherited source, which is cosmetic.

| Step | Component | Change |
|---|---|---|
| 1 | Preflight | No running Azure activity; PostgreSQL `Ready`; `platform_<env>` at `c9d2e4f6a8b1` |
| 2 | PROD only | On-demand PostgreSQL backup; `az acr import` the three digests into `crdijioneprod` |
| 3 | Database | `atwork_<env>` and `database-url-atwork`, derived from the server's existing URL |
| 4 | DijiAtWork | `atwork-release.bicep`, `environmentName=<env>`; what-if must show exactly 4 creates |
| 5 | DijiAtWork | Run `migrate-atwork-api`; `/health/deep` at `0003_atwork_notifications` |
| 6 | Platform Core | `migrate-platform-api` image to the release digest; run to `e1f3a5b7c9d0` |
| 7 | Platform Core | `platform-api` image to the same digest, with `ENTRA_INTERNAL_EMAIL_DOMAINS=dijitalteam.com` |
| 8 | Verify | Smoke test, plus every existing module's route and health; compare all images with the snapshot |

`e1f3a5b7c9d0` is data only: it sets the `atwork` row `ACTIVE` and enables the
`ATWORK_USER` baseline when `APP_ENV` is `uat` or `prod`. Default access still grants
nothing until that environment's Entra registration emits `acct` and step 7 sets the
domain list. Until then, access needs an explicit assignment.

`ATWORK_MANAGER` sees every employee. Assign it only to named people, ideally through
one Access Group, until team scoping exists.


Redeploy the previous image digests. To withdraw the Home card, disable the
`atwork` module in the Admin Center. Do not downgrade migrations in a shared
environment: the additions are backward compatible, and `0002` refuses to
downgrade while correction history exists. To stop alerts only, stop the job.

## Removal from an environment

1. Disable the `atwork` module row in the Admin Center.
2. Set `deployAtwork = false`. This does not delete what exists: incremental
   deployments leave resources in place, so delete `atwork-api`, `atwork-web`,
   `migrate-atwork-api` and `atwork-notifications-job` explicitly.
3. Retain or drop `atwork_<env>` and `database-url-atwork` as a separate, approved decision.

The two Platform Core additions (notification columns and delivery route) are
generic and stay.

## Decisions for initial DEV

- Notifications are in-app only. No email delivery yet.
- The current `ATWORK_MANAGER` permission bundle is retained, for a restricted DEV
  test group only.
- The missed check-out threshold stays at 12 hours.
- Attendance data is never deleted automatically.
- Workforce Directory integration and stronger audit protection are pre-production
  follow-ups.
- Deployment stays disabled and the module stays `COMING_SOON` until separately
  authorized.

## Platform Core migration integration

The unmerged branch `local/talent-module-admin` adds platform revision
`j0k1l2m3n4o5`, with `down_revision` `h8i9j0k1l2m3`. It exists on no remote branch.
This line's single head is `n4o5p6q7r8s9`, which descends from the same
`h8i9j0k1l2m3` through other revisions.

Keep every revision file unchanged. When that branch is integrated:

1. Add `j0k1l2m3n4o5` exactly as it is.
2. Add one empty Alembic merge revision with
   `down_revision = ("j0k1l2m3n4o5", "<current head>")`.
3. Confirm one head with `alembic heads`, then run `alembic upgrade head`.

Do not repoint `j0k1l2m3n4o5`, reset `alembic_version` or stamp a database forward. A
database already at `j0k1l2m3n4o5` would then skip the revisions that follow it.

Tested on disposable PostgreSQL 16, all ending at the merge revision with the expected
schema: empty; at `h8i9j0k1l2m3`; at `m3n4o5p6q7r8`; at `n4o5p6q7r8s9`; at
`j0k1l2m3n4o5`. A copy of a local SQLite database stamped `j0k1l2m3n4o5` also upgraded.

Before any hosted upgrade, read that environment's `alembic_version`. The expected
value is on this line's chain. Stop and investigate if it is anything else.
