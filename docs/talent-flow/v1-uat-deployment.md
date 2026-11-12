# DijiTalentFlow V1 UAT deployment

Status: executed in UAT and then in Production on 12 November 2026. See
`v1-release-record.md` for digests, results and rollback.

## Source and images

Build every image once from the merge commit of `release/talentflow-v1` into
`release/onsite-v1`, from a clean checkout, verify each image file by file
against that commit, then lock it (delete and write disabled). Record the
digests here before any UAT change.

| Image | Source | Built for |
|---|---|---|
| `platform-api` | merge commit | `platform-api`, `migrate-platform-api` |
| `talent-api` | merge commit | `talent-api`, `migrate-talent-api`, `talent-audit-outbox-job` |
| `recruitment-api` | merge commit | `recruitment-api`, `migrate-recruitment-api`, `recruitment-sync-job` |
| `shell-web` 1.0.2 | merge commit | `shell-web` (sign-in callback fix) |
| `talent-web` 1.0.2 | merge commit | `talent-web` |
| `talentflow-portal-web` 1.0.2 | merge commit | `talentflow-portal-web` |

DEV ran the same Talent, Recruitment and Platform source on isolated lines
(`d1ca2f9`, `ab13b4a`, `6f2d6be`). The merge adds only the release line's
existing commits, which are not TalentFlow code.

## Rollback images (current UAT, lock before starting)

| Resource | Digest |
|---|---|
| `platform-api`, `migrate-platform-api` | `sha256:17fa1f342ce5…` |
| `talent-api` | `sha256:7d3d9ea9ce66…` (`e1f77e4`) |
| `migrate-talent-api`, `talent-reconcile-job`, `bootstrap-talent-clients` | `sha256:ad5776134a1a…` |
| `recruitment-api`, its jobs | `sha256:04c2f76fdb82…` |
| `shell-web` | `sha256:6922d4845acd…` |
| `talent-web` | `sha256:f69e6c11d2cb…` |
| `talentflow-portal-web` | `sha256:f5d559d572e0…` |

Database recovery: `psql-dijione-uat` (B1ms, 7-day PITR). Record the recovery
point immediately before step 3. Restoring is a separate approved action.

## Platform scope

The release line already carries DijiAtWork's registration migrations. Outside
DEV they leave it inactive: the module stays `COMING_SOON`, and the
`ATWORK_USER` baseline row is created disabled. Both depend on `APP_ENV`, which
is set to `uat` on `platform-api` and `migrate-platform-api` (verified).

Platform migrations from UAT's head run through to `c9d2e4f6a8b1`: AtWork
registration and permissions (data only), notification `link_url` and
`dedupe_key`, module baseline roles, audit `event_id` (`a7e1d0c4b9f2`), and an
empty merge. `q7r8s9t0u1v2` (PR #89) is not part of the release.

## Sequence

Each step checks its result before the next; any failure stops the rollout.

1. Preflight, read-only: images and configuration captured, apps Healthy, no
   running jobs, PITR point recorded, rollback images locked.
2. Suspend `talent-reconcile-job` (`15 */6`), so the new code cannot run the
   first full import unattended.
3. Platform: `migrate-platform-api` to the new image, run, confirm head
   `c9d2e4f6a8b1`; then `platform-api`. Confirm `/health/deep`.
4. Recruitment: `migrate-recruitment-api` (adds `0003_sync_checkpoints`), then
   `recruitment-api`, then `recruitment-sync-job` image and
   `python scripts/run_scheduled_sync.py` args.
5. Talent: `migrate-talent-api` (adds `audit_outbox`, head `c4d6e8f0a2b3`),
   then `talent-api` with `EXTERNAL_PORTAL_BASE_URL=https://talentflow-portal-web.mangofield-96838df7.southeastasia.azurecontainerapps.io`.
6. Web: `shell-web`, `talent-web`, `talentflow-portal-web`. Confirm the
   `shell-web` custom domain stays bound.
7. Create `talent-audit-outbox-job` exactly as in DEV (Manual, 0.25 vCPU,
   0.5 GiB, 280 s, no retries, `python -m scripts.drain_audit_outbox`, the
   `id-dijione-uat` identity and the two Key Vault secrets). Run once manually,
   then set the five-minute schedule.
8. Run one sync to `COMPLETE`, then one reconcile through the internal endpoint
   (DEV: 37 s for 12,666 candidacies). Check the counts, then the audit backlog
   drains.
9. Resume `talent-reconcile-job` only on approval.

No resource sizes change. `recruitment-api` keeps `minReplicas=0`.

## Smoke tests

- Staff Entra sign-in and sign-out; a user without a role is refused.
- A crafted `/api/auth/callback?error=</script><script>…` renders as text.
- TalentFlow staff dashboard loads with data; a restricted-portfolio user sees
  only their clients.
- No application is client-visible after reconcile; no access grant exists.
- Unknown and untagged postings stay hidden.
- The audit drain runs succeed, with nothing pending after the backlog.
- Internal routes refused anonymously.

## Rollback

Reverse order, images only: web apps, `talent-api` and its jobs,
`recruitment-api` and its jobs, `platform-api` and its migrate job, each to
the digest above. The new schema is additive and ignored by the old images,
so no database restore is needed. Suspend `talent-audit-outbox-job` rather
than deleting it.
