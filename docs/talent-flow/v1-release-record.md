# DijiTalentFlow V1: release record

**Status:** in Production since 12 November 2026, open to staff only.
- Client access links are on hold until live-user acceptance is complete (see Follow-ups).
- Production URL: https://dijione.dijitalteam.com/talent-flow
- Client portal: https://talentflow-portal-web.icybush-52a8142b.southeastasia.azurecontainerapps.io

## Source

- **Release commit:** `0437a89f723b8ba11981a61f50ff2d8bf96909a1`, the squash merge of PR #92 into `release/onsite-v1`.
- **How the images were made:** built once from a clean checkout of that commit. The three API images were checked file by file against the commit.
- **UAT:** the images were deployed and validated there first.
- **Production:** the same images were copied by digest from `crdijionenonprod` to `crdijioneprod`, with no rebuild. Copies are locked against deletion and changes.

| Image | Digest | Used by |
|---|---|---|
| platform-api | `sha256:c5189226193dc1ed248eb86a274679bfba22d67d49853ee7d08a20dc9d090bc1` | `platform-api`, `migrate-platform-api` |
| talent-api | `sha256:afee55613199e7bacceeb82de8b796629a41eb1ef602eb9833a1595cf971fd7c` | `talent-api`, `migrate-talent-api`, `talent-audit-outbox-job` |
| recruitment-api | `sha256:54627a739fc1538d5aa1197e5d1238d6c468b268f5d29aae3004e80dcbae5470` | `recruitment-api`, `migrate-recruitment-api`, `recruitment-sync-job` |
| shell-web 1.0.2 | `sha256:628a0e594a78901a6fac144c988b497339236bc2b8f9f706c261fa0e05ed47ac` | `shell-web` |
| talent-web 1.0.2 | `sha256:3aad7d10ce49e83efdc844b3d7e32fa6d365a8829043f6c19751ec8440712326` | `talent-web` |
| talentflow-portal-web 1.0.2 | `sha256:85571c1ce68b528af47ab9c59a44e47229c131ee1d00ed3d3770eb0aa23764e4` | `talentflow-portal-web` |

`talent-reconcile-job` is not in the table. It only calls the internal reconcile endpoint with `curl`, so it keeps its earlier image, `sha256:ad5776134a1a…`, unchanged in every environment.

## Configuration changes

These changes are in addition to the image updates:

- **`talent-api`:**
  - `EXTERNAL_PORTAL_BASE_URL` was added, set to the portal URL for each environment.
  - The Azure CLI added empty values beside its secret references, and these were removed again.
- **`recruitment-sync-job`:**
  - Its command is now `python scripts/run_scheduled_sync.py`.
  - The Azure CLI side effect seen on `talent-api` was also corrected here.
- **`talent-audit-outbox-job`** (new):
  - Schedule: `*/5 * * * *`.
  - Resources: 0.25 vCPU, 0.5 GiB.
  - Runtime: 280 s timeout, no retries.
  - Command: `python -m scripts.drain_audit_outbox`.
  - Identity: the environment's managed identity.
  - Secrets: two Key Vault references, `database-url-talent` and `internal-service-secret`.

Unchanged:

- Resource sizes and replica counts.
- Custom domains: `shell-web` keeps `dijione.dijitalteam.com`.
- Every other application and job: Birthday, Onsite, People and Admin.

## Database migrations

Changes are additive. The previous images ignore the new columns and tables.

| Service | From | To | Content |
|---|---|---|---|
| Platform | previous head | `c9d2e4f6a8b1` | AtWork registration (outside DEV the module stays `COMING_SOON` and its role is disabled), notification link/dedupe, module baseline roles, audit `event_id` (`a7e1d0c4b9f2`), merge |
| Recruitment | `0002` | `0003_sync_checkpoints` | Sync checkpoints |
| Talent | `b3c5d7e9f1a2` | `c4d6e8f0a2b3` | `audit_outbox` |

## Results

| | UAT | Production |
|---|---|---|
| Sync | `COMPLETE`, first run | `COMPLETE`, first run |
| Rehearsal (changes rolled back) | Passed, 34.9 s processing | Passed, 34.8 s processing |
| Reconcile, run once | SUCCEEDED, 37.7 s | SUCCEEDED, 45.5 s |
| Candidates | 76 → 9,724 | 71 → 9,749 |
| Applications | 76 → 11,680 | 71 → 11,728 |
| Requests / verified mappings | 35 / 35 | 33 → 35 / 33 → 35 (2 new, both from a valid `DTC - <Client>` tag) |
| Duplicates, cross-client, applications on unverified postings | 0 | 0 |
| Client-visible applications / access links | 0 / 0 | 0 / 0 |
| Audit events delivered | 11,609; 0 pending | 11,668; 0 pending, 0 claimed |

Postings that are not mapped stay hidden. In Production that is 30 postings with an unknown client tag and 658 with no tag.

## Test evidence

- **Automated suites** (run locally on SQLite, never against a hosted database):
  - talent-api: 119 isolation, access-link, external-portal and visibility tests passed.
  - platform-api: 63 authentication, role, scope and Entra tests passed.
- **CI on PR #92:** green, except six known Birthday failures accepted as unrelated.
- **Hosted checks in both UAT and Production:**
  - Talent and portal APIs refuse anonymous requests, forged tokens and made-up access links (401).
  - The internal reconcile route refuses outside calls (401).
  - A crafted sign-in callback renders as text, so the XSS fix is live.
  - The pages load.

**Business acceptance**

| Scenario | Status |
|---|---|
| Staff sign-in and roles | Not live-tested; automated tests passed |
| Restricted portfolio isolation | Not live-tested; automated tests passed |
| Candidates hidden by default | Passed (0 visible in both environments) |
| Sharing a candidate | Not live-tested |
| Access links: refusing invalid ones | Passed |
| Access links: issue, redeem, revoke | Not live-tested |

The live-user script is `v1-uat-checklist.md`.

## Operations

- **`talent-reconcile-job`:**
  - Runs every 6 hours (`15 */6 * * *`).
  - It was suspended during the rollout and resumed with approval on 12 November at 16:38 UTC.
  - First scheduled run: 18:15 UTC.
- **`talent-audit-outbox-job`:** runs every 5 minutes. It succeeded on every scheduled run.
- **Monitoring:**
  - Today: job execution history and console logs in Log Analytics.
  - No alert rules exist yet (see Follow-ups).

## Rollback

Roll back in reverse order, by changing images only:

1. Web apps.
2. `talent-api` and its jobs.
3. `recruitment-api` and its jobs.
4. `platform-api` and its migration job.

Then suspend `talent-audit-outbox-job`; do not delete it. No database restore is needed.

| Resource | Production rollback digest (locked) |
|---|---|
| platform-api, migrate-platform-api | `sha256:17fa1f342ce5…` |
| talent-api and its jobs | `sha256:ad5776134a1a…` |
| recruitment-api and its jobs | `sha256:04c2f76fdb82…` |
| shell-web | `sha256:6922d4845acd…` |
| talent-web | `sha256:f69e6c11d2cb…` |
| talentflow-portal-web | `sha256:f5d559d572e0…` |

**Point-in-time recovery reference**, for a separately approved restore only:

| Server | Recovery point (UTC, 12 Nov 2026) | Retention |
|---|---|---|
| `psql-dijione-prod` | 15:10:11Z | 14 days |
| `psql-dijione-uat` | 07:36:24Z | 7 days |

## Follow-ups (none critical)

1. **Live-user acceptance before any client link.**
   - Staff sign-in by role, restricted-portfolio isolation, and issuing, redeeming and revoking an access link.
   - Until this passes, no access link may be issued to a client and no candidate may be shared.
2. **Alerting** (needs approval, because it creates Azure resources). Alert on:
   - failed `talent-reconcile-job` or `talent-audit-outbox-job` runs;
   - audit outbox rows pending for more than 30 minutes;
   - reconcile runs longer than 120 s.
3. **UAT reconcile schedule:** still suspended; resume when approved.
4. **TA data clean-up:** 30 postings carry a `DTC` tag whose client is unknown.
5. **CI:** the six failing Birthday tests are tracked separately.
