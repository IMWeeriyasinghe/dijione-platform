# 01: Current baseline (verified 13 Nov 2026, about 05:30 UTC)

[Start](00-START-HERE.md) · next [02 Application and architecture](02-APPLICATION-AND-ARCHITECTURE.md)

## Which version to continue from

| Meaning | Reference | Notes |
|---|---|---|
| **1. Latest available code** | `origin/release/onsite-v1` @ `75a9a3d` | V1 plus three AtWork commits (#94–#96). **Verified:** no changes after V1 to `apps/talent-api`, `talent-web`, `talentflow-portal-web`, `recruitment-api` or `shell-web` (`git diff --stat 0437a89 origin/release/onsite-v1 -- …` is empty) |
| **2. Latest approved development baseline** | **`origin/release/onsite-v1`**: new TalentFlow branches start from here | `main` (`e21fdb2`) is 102 commits behind; never branch from it |
| **3. Latest deployed TalentFlow** | V1 `0437a89` in UAT and Production; DEV on isolated pre-merge lines (table below) | platform-api everywhere is `88b9c08` (AtWork) |
| **4. Local-only Windows work** | See [Windows-only changes](#windows-only-changes) | Not on GitHub, so not on the Mac unless the copy included it |

**PR #93** (`docs/talentflow-v1-release`, `0b55ccb`, V1 release record): **draft, not merged** into `release/onsite-v1`. This handover package is on branch `docs/talentflow-handover`, with its own documentation PR to `release/onsite-v1`. That PR is independent of #93.


How each fact was checked:
- `az containerapp list/show` and `az acr manifest list-metadata`.
- A one-off read-only job execution against each database: `SET TRANSACTION READ ONLY`, counts only.
- `git fetch`.

Items marked **UNVERIFIED** say how to check them.

## Git

- **Remote:** `https://github.com/IMWeeriyasinghe/dijione-platform.git` (`origin`).
- **TalentFlow V1 release commit:** `0437a89f723b8ba11981a61f50ff2d8bf96909a1`, the squash merge of PR #92 into `release/onsite-v1`.
- **`origin/release/onsite-v1` now:** `75a9a3d`. On top of V1 it adds three DijiAtWork commits:
  - #94 `88b9c08`: AtWork UAT/Production release preparation.
  - #95 `96355ca`.
  - #96 `75a9a3d`.
- **`origin/main`:** `e21fdb2`, 102 commits behind the release line. Do not release from `main`.
- **Open documentation PR:** #93, a draft on branch `docs/talentflow-v1-release` (`0b55ccb`) that adds `docs/talent-flow/v1-release-record.md`. PRs #94–#97 exist; #94–#96 are merged AtWork work. **#97 is UNVERIFIED**: check it on GitHub.
- **Remote branch `origin/chore/deploy-prod-replica-floor`** (`60790cb`, 13 Nov): "keep PROD replica floors". It is not merged. It explains why Production `platform-api` and `shell-web` run with `minReplicas=1`.
- **Windows checkout:** on `feat/onsite-dashboard-v1` (`ab2f5f8`), with an uncommitted change to `deploy/README.md` that belongs to the owner. Local worktrees under `.worktrees/` (excluded through `.git/info/exclude`):

| Worktree | Branch | Purpose |
|---|---|---|
| `talentflow-v1` | `release/talentflow-v1` (`2bad33c`) | V1 release branch, merged as #92 |
| `talent-phase2` | `feat/talent-audit-outbox` (`d1ca2f9`) | Audit outbox, cold-start fix and batched reconcile (DEV line) |
| `talent-reconcile-uat` | `fix/talent-reconcile-cold-start` (`e1f77e4`) | Earlier reconcile fix, superseded by V1 |
| `platform-audit`, `platform-audit-dev` | Platform audit `event_id` branches | Superseded by V1 |
| `platform-callback` | `platform/callback-xss-usermenu` (`bb23145`) | Callback XSS fix, included in V1 |
| `v1-release` | `docs/talentflow-v1-release` | PR #93 |
| `handover` | `docs/talentflow-handover` | This package |

## Environment comparison (TalentFlow-relevant)

Subscription: **Dijital Team IT Production** (one subscription for all three environments).

| Item | DEV | UAT | Production |
|---|---|---|---|
| Resource group / container environment | `rg-dijione-dev` / `cae-dijione-dev` | `rg-dijione-uat` / `cae-dijione-uat` | `rg-dijione-prod` / `cae-dijione-prod` |
| Registry | `crdijionenonprod` | `crdijionenonprod` | `crdijioneprod` |
| Staff URL | `https://dijione-dev.dijitalteam.com` (custom domain **UNVERIFIED**; Azure host `shell-web.livelypebble-890e141a…`) | `https://dijione-uat.dijitalteam.com` | `https://dijione.dijitalteam.com` |
| Client portal | `talentflow-portal-web.livelypebble-890e141a.southeastasia.azurecontainerapps.io` | `talentflow-portal-web.mangofield-96838df7…` | `talentflow-portal-web.icybush-52a8142b…` |
| TalentFlow source | **Isolated DEV lines**: talent-api `d1ca2f9`, recruitment-api `ab13b4a`, web apps `ac4a04d`, shell `a9751be` | V1 `0437a89` | V1 `0437a89` |
| platform-api | `9318573c` (`88b9c08`, AtWork release) | `9318573c` (`88b9c08`) | `9318573c` (`88b9c08`) |
| talent-api | `7fc9c1fb` (`d1ca2f9`) | `afee5561` (V1) | `afee5561` (V1) |
| recruitment-api | `147f5969` (`ab13b4a`) | `54627a73` (V1) | `54627a73` (V1) |
| shell-web | `42db1bbd` (`a9751be`) | `628a0e59` (V1) | `628a0e59` (V1) |
| talent-web / portal | `7ba94b65` / `fccfec02` (`ac4a04d`) | `3aad7d10` / `85571c1c` (V1, 1.0.2) | `3aad7d10` / `85571c1c` (V1, 1.0.2) |
| migrate-talent-api / migrate-recruitment-api | `a93470b8` (`9b35f43`) / `d808f83e` (`5b1eec0`): **older images than the running APIs** | match the APIs | match the APIs |
| Platform head | `e1f3a5b7c9d0` | `e1f3a5b7c9d0` | `e1f3a5b7c9d0` |
| Talent head | `c4d6e8f0a2b3` | `c4d6e8f0a2b3` | `c4d6e8f0a2b3` |
| Recruitment head | `0003_sync_checkpoints` | `0003_sync_checkpoints` | `0003_sync_checkpoints` |
| `talent-reconcile-job` (`15 */6 * * *`) | **Suspended** | **Suspended** | **Active (Ready)**; succeeded 12 Nov 18:15 and 13 Nov 00:15 |
| `recruitment-sync-job` (`0 */6 * * *`) | Active | Active | Active |
| `talent-audit-outbox-job` (`*/5 * * * *`) | Active | Active | Active |
| Talent data | 34 requests, 9,698 candidates, 11,630 applications | 35 / 9,724 / 11,680 | 35 / 9,764 / 11,751 |
| Client-visible applications | 0 | 0 | 0 |
| Access links | 0 | 0 | **1 active (Access4)** |
| Audit outbox | all delivered (11,584) | all delivered (11,609) | all delivered (11,691) |
| Platform users (total / active / Entra) | 8 / 5 / 2 | 3 / 1 / 1 | 1 / 1 / 1 |
| TalentFlow roles | TA_MANAGER ×3, CUSTOMER_SUCCESS ×1 | TA_MANAGER ×1 | TA_MANAGER ×1 |
| `APP_ENV` | `development` | `uat` | `prod` |
| Auth | `AUTH_MODE=entra` on platform-api (DEV also allows dev identity; **UNVERIFIED**, check `DEV_IDENTITY_MODE`) | entra | entra |
| Lever | recruitment-api `INTEGRATIONS_MODE=live` | live | live |
| Email | `EMAIL_SENDING_MODE=mock` everywhere, so access links are copied from the screen | mock | mock |
| `EXTERNAL_PORTAL_BASE_URL` (talent-api) | each environment's own portal host | | |
| Replica floors | recruitment-api `min=1`, others 0 | all `min=0` | platform-api and shell-web `min=1, max=3`; others `min=0` |
| Modules | atwork ACTIVE, birthday ACTIVE, onsite ACTIVE, spark COMING_SOON, talent-flow ACTIVE | same | same |

### Known differences, and why

1. **DEV runs TalentFlow from isolated pre-merge branches,** not V1. Its behaviour matches V1, which was validated there on those lines (see `docs/talent-flow/v1-uat-deployment.md`), but its images were never rebuilt from `0437a89`. Bring DEV onto the release only with approval.
2. **DEV's migrate jobs run older images than its APIs.** The heads are correct now, but a future migration on DEV must set the migrate job's image first.
3. **`platform-api` is the AtWork release (`88b9c08`), not the V1 Platform image (`c5189226`).** The Platform head moved from `c9d2e4f6a8b1` (V1) to `e1f3a5b7c9d0`. The V1 rollback digest for platform-api in `v1-release-record.md` is therefore **out of date**: rolling Platform back now means rolling back the AtWork release too. Ask the AtWork release owner.
4. **AtWork is ACTIVE in UAT and Production.** That was a separate approved release; the V1 record described it as inactive.
5. **Reconcile schedules differ by design:** active in Production, suspended in DEV and UAT, each pending approval.
6. **Production's active Access4 link** is the only access link anywhere.

## Release images (V1, `0437a89`)

| Image | Digest | Status |
|---|---|---|
| talent-api | `sha256:afee55613199e7bacceeb82de8b796629a41eb1ef602eb9833a1595cf971fd7c` | UAT, Production |
| recruitment-api | `sha256:54627a739fc1538d5aa1197e5d1238d6c468b268f5d29aae3004e80dcbae5470` | UAT, Production |
| shell-web 1.0.2 | `sha256:628a0e594a78901a6fac144c988b497339236bc2b8f9f706c261fa0e05ed47ac` | UAT, Production |
| talent-web 1.0.2 | `sha256:3aad7d10ce49e83efdc844b3d7e32fa6d365a8829043f6c19751ec8440712326` | UAT, Production |
| talentflow-portal-web 1.0.2 | `sha256:85571c1ce68b528af47ab9c59a44e47229c131ee1d00ed3d3770eb0aa23764e4` | UAT, Production |
| platform-api (V1) | `sha256:c5189226193dc1ed248eb86a274679bfba22d67d49853ee7d08a20dc9d090bc1` | **Replaced** by `9318573c…` (AtWork) |

All V1 images and the pre-V1 rollback images are locked in their registries.

## Windows-only changes

Checked with `git status` per worktree, and by listing local branches that have commits on no remote.

| Item | Where | Action |
|---|---|---|
| This handover package | Pushed: `origin/docs/talentflow-handover` | The Mac fetches it ([06](06-MAC-CLAUDE-BOOTSTRAP.md)) |
| Uncommitted `deploy/README.md` edit | Main checkout (`feat/onsite-dashboard-v1`) | Owner's own edit; not TalentFlow. Leave it |
| Uncommitted edits to `shell-web` callback route, its test, and `UserMenu.tsx` | `.worktrees/platform-callback` | An earlier working copy of the callback XSS fix. **The fix shipped in V1.** Diff against `0437a89` before discarding |
| Branches with commits on no remote, not merged: `local/talent-module-admin` (4, Module Admin design and docs), `local/dev-env-deterministic` (2, dev docs), `local/ui-ux-brand-verification` (1, design-system wordmark) | **Windows only.** Not pushed, by owner decision (13 Nov) | Kept on Windows. The owner will decide separately whether to push them; until then they are not on the Mac |
| Other unpushed branches (`feat/client-portfolio-*`, `feat/grant-expiry-extend`, `feat/posting-mapping-unmap-reopen`, `feat/talent-web-*`, `pr-43`, …) | Local branches, upstream deleted | Already **squash-merged** (their subjects appear on the release line). No action |
| `apps/talent-api/.env`, `apps/recruitment-api/.env` (Lever key), `apps/birthday-api/.env` | Ignored files | **Contain secrets.** Never copy them into docs or chat. The owner decides whether to move them by hand; the Mac can run with `.env.example` and mock mode |
| `.local-backups/*-backup-20260902-*.db` | Ignored | **May contain real candidate data.** Do not transfer or open without the owner's decision |
| Local SQLite files (`*.db` under `apps/`) | Ignored | Dev data; regenerate with the seed scripts |
| Deployment runbooks and probe scripts from the V1 rollout | Were in a temporary folder outside the repository | **Copied into [runbook/](runbook/README.md)** for reference |
| V1 rollout evidence (JSON snapshots, logs) | Same temporary folder (`state-*`) | Not copied: it contains client names and posting ids. The summary is in `docs/talent-flow/v1-release-record.md` |

## How to re-verify

The commands are in [06 bootstrap](06-MAC-CLAUDE-BOOTSTRAP.md#read-only-verification-commands). Database checks need a one-off job execution with an inline read-only script. That is a hosted action: read-only, but it starts a container, so ask first.
