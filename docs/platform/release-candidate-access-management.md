# Access-management release candidate

Everything below is **local or CI only until approved**. Nothing here has been deployed, no hosted
migration has been run, and no hosted configuration has been changed.

## 1. What is in it

| # | Workstream | Where it lives | State |
|---|---|---|---|
| D9 | Staff-session boundary: `platform-api` accepts only a DijiOne user's own staff session (a supplier-portal token can no longer authenticate as the DijiOne user with the same number) | PR #112, merged as `e00b3b6` on `release/onsite-v1`. `platform-api` only; no migration | **Merged, not deployed** |
| D1–D8 | Effective roles on `/me`, session refresh endpoint, case-insensitive Entra email match, Add User, explicit client scope, unique assignments, removable/restorable default access, per-user audit history | Draft PR #113 (`fix/admin-access-management`) | CI green, draft |
| Diag | Effective Access Diagnostics (read-only endpoint, admin-api pass-through, user Diagnostics tab) | PR #113 | CI green, draft |
| D2 | Session revocation: per-user `access_version`, `av` claim, internal snapshot feed, cached `RevocationGuard` (FRESH / STALE / RESTRICTED), explicit per-route policy, web refresh and retry. **Token lifetime unchanged (12 h)**; off unless `REVOCATION_ENABLED` | PR #113 | CI green incl. PostgreSQL 16, draft |
| View-as | Read-only simulation of an internal employee by a Super Admin | branch `feat/view-as-user` (on top of PR #113), local, **not pushed** | Complete locally |

Applications touched: `platform-api`, `admin-api`, `talent-api`, `birthday-api`, `onsite-api`, `atwork-api`,
`spark-api` (never deployed), shared `auth-client-py`, and the web apps through the shared `auth-client-ts`
(`shell-web`, `admin-web`, `talent-web`, `birthday-web`, `onsite-web`, `atwork-web`; `talentflow-portal-web`
and `birthday-supplier-web` take no behavioural change).

## 2. Migrations (additive, run in this order, `platform_dev` only)

| Order | Revision | Effect |
|---|---|---|
| 1 | `g3h5j7k9m1n2` | Unique constraints on `user_module_roles(user_id, module_key)` and `group_module_roles(access_group_id, module_key)`; `audit_logs.subject_user_id` (+ index, back-fill). **Stops without changing anything if duplicate assignments exist.** |
| 2 | `h4j6k8m0n2p3` | `users.access_version BIGINT NOT NULL DEFAULT 0` |
| 3 | `i5k7m9n1p3q4` | `view_as_sessions` table; permission `platform.admin.view_as` linked to `SUPER_ADMIN` only; raises every `access_version` |

**Mandatory gates before each environment** (read-only until the last step; no data cleanup is authorised):

1. Current revision is the expected pre-migration head.
2. Duplicates: `SELECT user_id, module_key, count(*) FROM user_module_roles GROUP BY 1,2 HAVING count(*)>1;` and
   `SELECT access_group_id, module_key, count(*) FROM group_module_roles GROUP BY 1,2 HAVING count(*)>1;`
   must both return no rows. Any row is a stop for a human decision.
3. Volume: `SELECT count(*) FROM audit_logs;`. Migration 1 back-fills row by row and builds an ordinary index.
   Roughly 100,000 rows or more needs a batched back-fill and a concurrent index first (ask before changing it).
4. A restore point exists (PITR window or on-demand backup) and a `pg_dump` of `platform_dev` is taken.
5. Run `migrate-platform-api` **with the new image, before the new code starts** (`deploy.sh` swaps workloads
   before migrate jobs; for this release update the job image and run it first). Set a `lock_timeout`.
6. Verify `alembic_version`, the constraints, the column and the table, and `/health/deep`.

Verified on PostgreSQL 16 in CI for migrations 1 and 2 (PR #113: `pg (platform-api)` upgrade, downgrade to base,
upgrade, full suite). Migration 3 is covered on SQLite locally and will be covered by CI once pushed.

## 3. Switches (all default to today's behaviour)

| Setting | Where | Default | Purpose |
|---|---|---|---|
| `REVOCATION_ENABLED` | each of talent, birthday, onsite, atwork APIs | off | Enforce revocation from the cached snapshot. Needs `PLATFORM_API_URL` (already `http://platform-api`) and `INTERNAL_SERVICE_SECRET` (already mounted). A wrong value stops the service starting. |
| `REVOCATION_REFRESH_SECONDS`, `_FRESH_SECONDS`, `_RESTRICTED_SECONDS` | same | 30 / 300 / 3600 | Timings (finite, above zero) |
| `VIEW_AS_ENABLED` | `platform-api` | **off** | Allow starting View-as sessions. Also the kill switch. |
| `VIEW_AS_MINUTES` | `platform-api` | 30 | Session length |
| `JWT_EXPIRES_MINUTES` | `platform-api` | 720 | **Not changed by this release.** Reducing to 60 is a separate, later approval. |

Enforcement of read-only for a View-as token in the applications is **always on** (it needs no flag).

## 4. Rollout order for each environment (DEV, then UAT, then PROD)

1. **D9 first, on its own** (see `docs/platform/` runbook below). Smoke, soak, then the next environment.
2. Access release, in this order, with the gates of section 2:
   1. `platform-api`: migration job (new image) → run → swap `platform-api` image.
   2. Application APIs (talent, birthday, onsite, atwork) with the new library, `REVOCATION_ENABLED` unset.
   3. Web apps (banner, refresh/retry, `authorizedFetch`) and `admin-web`.
   4. Verify `/health/deep` shows `revocation.enabled=false` and the migration up to date.
3. Switch on, one environment at a time, only after step 2 is complete in that environment:
   1. `REVOCATION_ENABLED=true` on the four APIs; confirm `/health/deep` reports `FRESH` with a snapshot.
   2. `VIEW_AS_ENABLED=true` on `platform-api`. **Never before every user-token API in the environment runs the new
      library** (an old API ignores the View-as token's claim and would authorize it for changes).
4. Later, separately approved: `JWT_EXPIRES_MINUTES=60`.

Hosted facts that must be confirmed before enabling revocation: `platform-api` runs with minimum replicas 0 in DEV
(the 30-second feed polling will keep it awake), and every API's `PLATFORM_API_URL` resolves.

## 5. Rollback

| Change | Rollback |
|---|---|
| View-as | `VIEW_AS_ENABLED=false` (immediate for new sessions; running ones end within 30 minutes) |
| Revocation | `REVOCATION_ENABLED` unset, redeploy the API (a configuration change) |
| Application / web code | Redeploy the previous image digest; keep a recorded digest per service |
| Migrations | All additive. Leave them in place when rolling code back (old code ignores the column and tables). Downgrade only if required, using the new image. After any database **restore**, run `python -m app.services.access_version` to revoke older sessions. |

## 6. D9 DEV runbook (operator-run; nothing executed)

Read-only facts gathered from DEV (not assumed from the repository): `platform-api` runs
`crdijionenonprod.azurecr.io/dijione/platform-api@sha256:662d84dfd49643cd9c33c7a1c80aa9562a8d828d2175202019a36cbca9a89b84`
(tag `b4aa3d6`, revision `platform-api--0000026`, healthy, single-revision mode, min 0 / max 1 replica, internal
ingress), `migrate-platform-api` is on the same digest and last ran `Succeeded`, `AUTH_MODE=entra`, `birthday-api`
`SUPPLIER_AUTH_MODE=entra`. Between `b4aa3d6` and `e00b3b6` the only `platform-api` change is the D9 fix.
No image for `e00b3b6` exists yet.

1. From a clean checkout of `e00b3b6`: `az acr build -r crdijionenonprod -f deploy/Dockerfile.api --build-arg SERVICE=platform-api -t dijione/platform-api:e00b3b6 .`; record the digest (`az acr repository show -n crdijionenonprod --image dijione/platform-api:e00b3b6 --query digest -o tsv`).
2. `az containerapp update -g rg-dijione-dev -n platform-api --image crdijionenonprod.azurecr.io/dijione/platform-api@<new digest>`
3. `az containerapp job update -g rg-dijione-dev -n migrate-platform-api --image crdijionenonprod.azurecr.io/dijione/platform-api@<new digest>` (keeps the job on the same image; it has nothing to migrate).
4. Check the new revision is `Healthy` and the logs are clean; `/api/auth/config` through the gateway answers.
5. Smoke: a staff session started **before** the swap still works; a new staff sign-in works; the Admin Center users list loads; a DijiBirthday supplier-portal sign-in and order list work; **a supplier-portal token presented to `/api/auth/me` and `/api/platform/admin/users` returns 401** (take the token from the browser; never paste it anywhere).
6. **Rollback:** the same two `update` commands with `sha256:662d84dfd49643cd9c33c7a1c80aa9562a8d828d2175202019a36cbca9a89b84`. Sessions issued by the new image still work on the old one.

Follow-up (separate small PR, at least 12 hours after the deploy in each environment): make `actor_type=staff`
mandatory in `_is_staff_session`.

## 7. Evidence

| Check | Result |
|---|---|
| PR #112 CI | 45/45 incl. `postgres` workflow |
| PR #113 CI (head `e2c347e`) | all green incl. `pg` for platform, talent, birthday, people, recruitment, commercial; gitleaks; module guard |
| View-as branch, local | platform-api 297, auth-client-py 102, talent 394, birthday 378, onsite 257, atwork 156, spark 10, admin-api 18; web: shell 131, admin 30, talent 82, birthday 102, onsite 93, atwork 40, portal 16, supplier 30; ruff, eslint, tsc, module-independence guard clean |
| Independent security reviews (Opus) | D2: 10 findings, release-relevant ones fixed. View-as: see the final report |

## 8. Approvals required

1. D9 deployment to DEV, then UAT, then PROD (each separately).
2. Pushing `feat/view-as-user` and opening its PR.
3. Merging PR #113 (and the View-as PR), after review.
4. The hosted gates in section 2 (read-only checks, backup), per environment.
5. Each hosted migration run, each configuration change in section 3, and any change to `JWT_EXPIRES_MINUTES`.

## 9. Accepted residual risks

* A group-grant removal racing a concurrent membership insert can leave one refreshed token carrying the removed
  grant until it expires (bounded by token lifetime).
* A revocation takes up to about 35 seconds to reach every replica, and bulk personal data is served only while the
  snapshot is current; ordinary reads continue during a feed outage, writes and exports do not.
* Birthday supplier impersonation tokens (an existing feature) are not covered by user revocation.
