# Diji On-site — Module removal test and runbook

The module-removal test is a **required acceptance gate** (architecture
rule 7). It proves that Diji On-site has no dependents: disabling or
removing it never affects any other DijiOne application or its data.

## Scenario

`onsite-api`, `onsite-web`, the `onsite_<env>` database, `onsite-sync-job`
and `job-migrate-onsite-api` are disabled or removed, and the `onsite`
module registry row is disabled.

## Acceptance criteria

| Criterion | Automated (`module-boundaries` workflow, *planned PR 1.4*) | Deployed drill (DEV) |
|---|---|---|
| DijiBirthday continues | birthday-api tests; birthday-web and birthday-supplier-web build with `apps/onsite-*` deleted | Dashboard and upcoming load; `people-sync-job` and `birthday-scan-job` succeed |
| DijiTalentFlow continues | talent-api tests; talent-web and talentflow-portal-web build | Dashboard loads; `recruitment-sync-job` succeeds |
| DijiAdmin continues | admin-api tests; admin-web builds | Users, groups and applications pages load; On-site shows as disabled |
| people-api continues | people-api tests (Employee contract and Workforce Directory) | `/api/people/freshness` and `/api/people/workforce-directory/freshness` OK |
| platform-api continues | platform-api tests; `alembic upgrade head` on a fresh database | Sign-in, `/api/auth/me`, `/api/modules` without the On-site card |
| No other app's migration needs reverting | Every other service's `alembic upgrade head` succeeds with On-site deleted | Nothing reverted; the registry row is only disabled |
| No other runtime path references `onsite-api` | `scripts/check-module-independence.js` finds no On-site tokens outside `apps/onsite-*` and the allow-listed registration points, and none at all in people-api, talent-api, birthday-api, admin-api, recruitment-api or shared packages | Ingress logs show no callers of `onsite-api` other than the shell gateway and its own job |
| shell-web | Builds | `/onsite` fails on its own; every other route works |

## Automated job (planned PR 1.4)

1. Delete `apps/onsite-api` and `apps/onsite-web`.
2. Remove the `apps/onsite-web` workspace entry, then `npm install`.
3. Run pytest and `alembic upgrade head` for platform, people, birthday,
   talent, admin and recruitment.
4. Build every remaining web app.
5. Run the module-independence guard.

Runs on PRs touching `apps/onsite-*`, registration points, `packages/` or
`deploy/`, and weekly. The repository owner makes it a required status check.

## Deployed drill (DEV, Phase 1 step O8)

1. Disable the `onsite` registry row (Admin Center → Applications).
2. Stop `onsite-sync-job`; scale `onsite-api` and `onsite-web` to zero.
3. Run the "Deployed drill" checks in the table above.
4. Restore, run "Sync now", confirm the mirror is intact.

## Permanent removal runbook

1. Disable the `onsite` registry row.
2. Deploy with `deployOnsite=false`.
3. Delete `onsite-api`, `onsite-web`, `onsite-sync-job` and
   `job-migrate-onsite-api` explicitly — incremental Bicep deployments do not
   delete resources removed from the template.
4. Optionally drop `onsite_<env>` and the `database-url-onsite` Key Vault
   secret.
5. The On-site SQL Entra admin runs `DROP USER [dijione-onsite-api-<env>]`.

The `people-api` Workforce Directory stays: it is a generic People
capability, not part of the On-site module.
