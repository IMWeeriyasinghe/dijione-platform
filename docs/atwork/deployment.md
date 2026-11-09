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

## Order of operations (after approval)

1. Build every changed image: `platform-api` and `shell-web` must be redeployed
   too. `shell-web` needs a rebuild because rewrites are fixed at build time.
2. `DEPLOY_ATWORK=true`, and `deployAtwork = true` in the DEV parameters for both
   templates. Deploy the foundation and run `init-secrets.sh`.
3. Migrate `platform-api` first (`n4o5p6q7r8s9`), then `atwork-api`
   (`0003_atwork_notifications`).
4. Deploy workloads and run the smoke test. Change `COMING_SOON` only when approved.

## DEV smoke test

- [ ] `/health/deep` on `atwork-api` reports the database OK and the migration up to date.
- [ ] Sign in through `shell-web`; `/atwork` opens with no second sign-in.
- [ ] An `ATWORK_USER` is refused `/atwork/management`.
- [ ] Check in, break, end break, confirm check-out, check in again; totals add up.
- [ ] Submit a missing-session request. A reviewer gets a notification that opens it.
- [ ] The requester does not get the reviewer notification.
- [ ] Approve and reject another; the employee is notified, with the reason on rejection.
- [ ] Start `atwork-notifications-job` manually; it succeeds. A second run creates nothing new.
- [ ] Download CSV and Excel; check filename, time zone and Export Information.

## Rollback

Redeploy the previous image digests. Do not downgrade migrations in a shared
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

## Platform Core migration integration precautions

The unmerged branch `local/talent-module-admin` adds platform revision
`j0k1l2m3n4o5`, with `down_revision` `h8i9j0k1l2m3`. This branch's single head is
`n4o5p6q7r8s9`, which descends from that same `h8i9j0k1l2m3` through other revisions.

- When that branch is integrated, repoint `j0k1l2m3n4o5` to the head current at that
  time, so there is one head. Do not add a merge revision to hide the fork.
- Confirm one head with `alembic heads` and test on disposable PostgreSQL before
  merging. Repointing changes the migration order, so also test that the seed is idempotent.
- A local database stamped `j0k1l2m3n4o5`, such as the old local `platform.db`, has
  not run the later revisions. After repointing, Alembic would treat them as already
  applied and silently skip them. Do not upgrade such a database in place: rebuild a
  copy from migrations and seed data, and keep the original.
- Check every hosted environment's `alembic_version` before integration.
