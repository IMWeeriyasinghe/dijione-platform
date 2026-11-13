# Git, release and rollback workflow

## Branch facts (fetched 2026-11-13)

### DijiOne (`github.com/IMWeeriyasinghe/dijione-platform`)
| Branch | Role | Head |
|---|---|---|
| `release/onsite-v1` | **The integration line for the whole platform** (On-site, Birthday, TalentFlow, DijiAtWork PRs #80–#108 merged here). All three environments are built from it. Start new On-site work from here. | `7eabdc6` |
| `docs/onsite-handover` | This handover package (from `7eabdc6`), pushed, **not merged** | see `git log` |
| `feat/onsite-dashboard-v1` | Historical On-site feature branch; its On-site code equals the release branch (only deploy/docs differences). Do not base new work on it. | `1d9785c` |
| `main` | Stale (TalentFlow era, `e21fdb2`); not the deployment source | — |
| `docs/birthday-handover` | Another workstream's handover; ignore | — |

Many other local-only branches on the Windows PC belong to other workstreams; none contain unpushed On-site work.
The Windows working tree was **clean** when this package was written; the earlier local `deploy/README.md` edit
had already been committed (`0a552a9`, content identical). PRs are created by the user on GitHub (`gh` is not
installed on the Windows PC); open-PR state was not queried — check on GitHub.

### DijiOnsite-Agent (`github.com/IMWeeriyasinghe/DijiOnsite-Agent`)
| Branch | Head | Notes |
|---|---|---|
| `main` | `d18e882` | in sync with origin |
| `docs/mac-handover` | — | adds `docs/handover/MAC-HANDOVER.md` and the previously **untracked** `deploy/production-pc/export-employee-directory.ps1`; pushed, not merged |

## Two-machine rules (Windows ↔ Mac)
1. `git fetch --all --prune` before starting; check `git status` is clean.
2. One branch per task; never work on the same branch on both machines at once.
3. Commit small, focused changes; push your branch; the user reviews and merges (PR).
4. Before switching machines: commit + push, then on the other machine fetch and confirm the same SHA.
5. Never assume an uncommitted file on one machine exists on the other.
6. No force-push, no history rewrite, no merges into `release/onsite-v1`/`main` without approval.

Verify on the Mac:
```bash
cd "/Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform"
git remote get-url origin && git status --short && git fetch --all --prune
git rev-parse --short origin/release/onsite-v1 origin/docs/onsite-handover
git switch -c onsite/<task> origin/release/onsite-v1      # new work
```

## Release workflow (established, used for every On-site release)
1. Implement on a branch from `release/onsite-v1`; run the suites (MAC-DEVELOPMENT-SETUP.md).
2. Merge to `release/onsite-v1` (user approval).
3. Build only changed images from that commit:
   `az acr build -r crdijionenonprod -f deploy/Dockerfile.api --build-arg SERVICE=onsite-api -t dijione/onsite-api:<tag> .`
   (`Dockerfile.web --build-arg APP=onsite-web --build-arg GIT_SHA=<sha> --build-arg BUILD_DATE=<utc>` for the web).
   Record digests (`az acr repository show -n crdijionenonprod --image dijione/<svc>:<tag> --query digest`).
4. **DEV**: if migrations changed, update + start `migrate-<svc>` first and wait for Succeeded; then
   `az containerapp update --image <registry>/dijione/<svc>@<digest>` for the app and
   `az containerapp job update --image …` for `onsite-sync-job` and `migrate-onsite-api` (keeps cron/timeout).
   people-api changes: migrate job → app → wait for single active revision → start `people-workforce-sync-job`.
5. DEV smoke: `/onsite` 200, `/api/onsite/metadata` 200, data APIs 401 unauthenticated, revisions Healthy,
   `onsite-sync-job` executions Succeeded, read-only in-container checks (VALIDATION-CHECKLIST.md).
6. **UAT**: same digests, same order, same checks.
7. **PROD (approval gate)**: `az acr import -n crdijioneprod --source crdijionenonprod.azurecr.io/dijione/<svc>:<tag> --image dijione/<svc>:<tag>`
   (digest preserved — verify), then the same steps against `rg-dijione-prod`. Agents may not read PROD data
   in-container; verify via UI/health/job status.
8. Post-deploy: sync executions for 10 min in all envs, Azure SQL DTU (should stay ~0–5 %).
Only touch On-site apps/jobs (+ people-api when it changes). Never redeploy other modules' apps for On-site work.
A full `main.bicep`/`onsite-release.bicep` run requires a what-if review first and correct On-site parameters
(INFRASTRUCTURE-ENVIRONMENTS.md "Remaining risk").

## Rollback
Point the app/jobs back at the previous digest (`az containerapp update --image …@<previous>`). Migrations
are additive (`onsite 0001`, `people 0004` add-column) — older images work against the newer schema; never
downgrade a database for rollback. Previous On-site digests (before 2026-11-04 photo release):
onsite-api `sha256:194396f2194d6b3c0c4f991372491d61d05d3d12f41d77778d61ef668148ddfd`,
onsite-web `sha256:c19b3790d9644d420f38c71614035bddd9db731429afcae842215c2802b18b4b`,
people-api UAT/PROD `sha256:ff01e9a202049257ff543966e01261013a823669f33baae27e8878d8fc77b3b3`.

## Separate release tracks
| Component | How it ships |
|---|---|
| Diji On-site (DijiOne) | Container images as above |
| Diji On-site Attendance | Agent repo `deploy/azure/attendance/deploy-attendance.ps1` (App Service + SQL schema); schema changes additive + approved; affects every environment at once |
| Diji On-site Agent | Installer on the production PC by an operator; never automated |
