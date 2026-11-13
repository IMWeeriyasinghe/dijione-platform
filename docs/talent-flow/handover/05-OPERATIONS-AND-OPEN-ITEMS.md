# 05: Operations, decisions and open items

[Start](00-START-HERE.md) · prev [04](04-GIT-AND-MIGRATION-PLAN.md) · next [06 Bootstrap](06-MAC-CLAUDE-BOOTSTRAP.md)

## Azure environments

See the comparison in [01](01-CURRENT-BASELINE.md#environment-comparison-talentflow-relevant). The full V1 record is `docs/talent-flow/v1-release-record.md` (PR #93). The rehearsed plan is `docs/talent-flow/v1-uat-deployment.md`.

## V1 deployment procedure (known good; do not run without approval)

The scripts are in [runbook/](runbook/README.md). Each phase checks its own gate and stops on failure.

1. **Preflight (read-only).**
   - Save every app and job definition to JSON.
   - Confirm each app's latest revision is Healthy and no job is running.
   - Record the point-in-time recovery time and the rollback digests.
2. **Lock** the rollback images: `az acr repository update --delete-enabled false`.
3. **Images.**
   - Build each image **once** from a clean checkout of the merge commit with `az acr build` (`deploy/Dockerfile.api` with `SERVICE=…`; `deploy/Dockerfile.web` with `APP`, `GIT_SHA`, `BUILD_DATE`).
   - Verify each API image file by file against the commit (`imgverify.py`), then lock it against delete and write.
   - **Production:** `az acr import` from `crdijionenonprod` **by digest**, confirm the digest is identical, then lock. Never rebuild for Production.
4. **Suspend `talent-reconcile-job` before any Talent change:** ARM `POST …/suspend?api-version=2026-07-01`.
5. **Create or check `talent-audit-outbox-job`** (`jobcheck.py`: 16 checks).
6. **Platform:** set the `migrate-platform-api` image, run it, and confirm its log shows the expected head. Then update `platform-api`.
7. **Recruitment:** `migrate-recruitment-api`, then `recruitment-api`, then the `recruitment-sync-job` image and args.
8. **Talent:**
   - Run `migrate-talent-api` and gate on: the head, an empty outbox, and data unchanged.
   - Update `talent-api`.
   - Set `EXTERNAL_PORTAL_BASE_URL`, with a strict environment comparison afterwards.
9. **Web:** shell-web, talent-web, portal. **Check the shell-web hostnames are unchanged** (custom domain).
10. **Audit:** one manual drain, then the `*/5` schedule.
11. **Sync:** run `recruitment-sync-job` until freshness is `COMPLETE` (at most 4 runs).
12. **Reconcile.**
    - Run a rehearsal inside a transaction that is rolled back (`c2_body_rehearsal.py`). It must show: source COMPLETE, SUCCEEDED, 0 conflicts or ambiguous mappings, existing VERIFIED mappings unchanged, new mappings only from valid DTC tags, and processing under 180 s.
    - Run **exactly one** real reconcile (`c2_body_run.py`).
    - Check the integrity gate: 0 duplicates, 0 cross-client requests, 0 applications on unverified postings, grants and visibility unchanged, and the counts add up.
13. **Drain:** wait for the scheduled job to empty the outbox, with no failures among scheduled executions.
14. **Smoke tests:**
    - pages return 200 and `/api/auth/config` reports `entra`;
    - anonymous and forged calls to talent APIs get 401;
    - the internal reconcile URL gets 401;
    - a made-up portal link gets 401;
    - a crafted callback renders as text.
15. **Resume the schedule** only with separate approval: ARM `POST …/resume`.

### Lessons learned and constraints

**Azure CLI side effect**
- `az containerapp update` can add `value: ""` beside a Key Vault `secretRef`, or remove one.
- **The approved fix:** patch only those entries back to their exact pre-change form through ARM (`PATCH`, api-version `2025-10-02-preview`), then re-run the strict comparison (`secretref_fix` in the runbook).
- That patch is sometimes refused ("resource definition is invalid") when nothing needs changing. The strict comparison decides whether it matters.

**Strict configuration comparison (`cfgcmp.py`)**
- After every app change, the whole configuration must equal the pre-change copy, apart from the allowed fields: the image, plus `EXTERNAL_PORTAL_BASE_URL` on talent-api.
- Job changes are compared field by field.

**Jobs**
- Change job images and args through ARM, not the CLI. The CLI once rewrote a job's environment, and it cannot pass `-m` as an argument.
- Run database checks as a one-off **job execution with an override**: inline base64 code, secrets as `secretRef`, read-only transaction, and a result line prefixed `C2R ` read from Log Analytics. Never use `containerapp exec`; it was throttled and unreliable.
- Count only numeric-suffixed executions as scheduled runs. Override runs have random suffixes.

**Bicep and capacity**
- **Never run a full `main.bicep` deployment.** It drops custom domains and ad hoc settings.
- Keep the 220 s reconcile budget. Do not raise it, and do not change capacity without approval.

**Never**, in any of this: run a destructive point-in-time restore automatically, or write to Lever, HubSpot or BambooHR.

### Rollback

**Order (images only):**
1. Web apps.
2. talent-api and its jobs.
3. recruitment-api and its jobs.
4. platform-api.

Then suspend the audit job (do not delete it). **The schema changes only add things**, so no database restore is needed.

**Production pre-V1 rollback digests (locked):**

| App | Digest |
|---|---|
| talent | `ad577613…` |
| recruitment | `04c2f76f…` |
| shell | `6922d484…` |
| talent-web | `f69e6c11…` |
| portal | `f5d559d5…` |

**Platform is now on the AtWork release.** Coordinate any Platform rollback with that release's owner.

**Point-in-time recovery references:** Production 12 Nov 15:10:11Z (14 days); UAT 12 Nov 07:36:24Z (7 days). These are for a separately approved restore only.

### Monitoring today

- **What exists:** job execution history (`az containerapp job execution list`) and Log Analytics console logs.
- **What doesn't:** **no alert rules** and no Application Insights.
- **Reconcile outcomes are reliable signals:** a failed reconcile now returns 503, so `curl -f` fails the job, and PARTIAL is logged as a warning.

## Decisions to preserve (with reasons)

| Decision | Reason |
|---|---|
| **Lever is the recruitment source; DijiOne reads it only (GET)** | Lever is the business system of record. A write could disrupt live recruitment. This is a contract rule (`CLAUDE.md` §60) |
| **`DTC - <Client Name>` tag, not HubSpot, identifies a posting's client** | It is deliberately maintained by TA and lives on the posting itself. HubSpot has no recruitment data, and adding it would create a dependency for no benefit |
| **Mappings must be VERIFIED; unmatched postings stay hidden** | Client visibility is an authorization decision, so it must fail closed. A tag never creates a client, and a manual mapping wins |
| **No manual creation of requests or candidates** (403 routes kept) | Data comes from Lever. Manual records would drift from the source and break deduplication |
| **Client scope enforced in the backend on every query** | The UI is not a security boundary. Restricted portfolios must not leak |
| **Every application hidden until shared** | Clients must see only curated candidates |
| **Access links: hashed token, 1–90 day expiry, revocable, re-checked every request, separate signing secret** | Clients have no accounts. A link must be cheap to cut off and impossible to replay after revocation |
| **Build once, promote the same digest; lock images** | What was tested is exactly what runs, and rollback targets cannot disappear |
| **DEV → UAT → Production with gates; reconcile suspended during change** | Stops unattended imports on half-migrated schemas |
| **Transactional audit outbox with `event_id` deduplication** | Audit events cannot be lost or duplicated if Platform is slow or down |
| **Batched reconcile, synchronous with honest outcomes** | It used to time out silently and report success. Now it takes about 40 s and its status is real |

## Open items

Priorities: **P1** release follow-up; **P2** operational; **P3** technical debt; **F** future enhancement.

| # | Item | Type | Priority | Status / next step |
|---|---|---|---|---|
| 1 | **Production has an active access link for Access4.** Issued 13 Nov 04:49 UTC, redeemed once, expires 27 Nov, contact address outside Dijital Team. **It conflicts with the hold on client links until live acceptance passes.** No candidates are shared, so only request-level information is visible | Business acceptance / security | **P1, urgent decision** | Owner confirms whether this was intended. If not, revoke it at `/talent-flow/access-links` (owner action, or an approved one) |
| 2 | Live-user acceptance: sign-in by role, restricted isolation, share a candidate, link issue, redeem and revoke | Business acceptance | P1 | Script: `docs/talent-flow/v1-uat-checklist.md`. Testers T1 and T2 were approved but not activated |
| 3 | Rollout of client sharing | Business acceptance | P1 | Only after item 2 passes and the owner signs off |
| 4 | Alert rules: failed reconcile or audit job, outbox pending over 30 min, reconcile over 120 s | Operational | P2 | Needs approval (creates Azure resources) |
| 5 | UAT and DEV `talent-reconcile-job` suspended | Operational | P2 | Resume with approval |
| 6 | 30 Production postings with a `DTC` tag naming an unknown client, and 658 untagged | Data quality | P2 | TA fixes tags in Lever, or a platform admin adds the missing clients. Never auto-create them |
| 7 | PR #93 (release record), draft | Documentation | P2 | Mark ready and merge. Update its Platform rollback note, since platform-api is now the AtWork image |
| 8 | Handover PR (documentation only) | Documentation | P2 | Merge after owner review |
| 9 | DEV runs pre-merge TalentFlow images; DEV migrate jobs run older images | Technical debt | P3 | Optionally align DEV to `0437a89` (approval) |
| 10 | Redeem rate limiter keyed on the proxy IP (`request.client.host`) | Technical debt (fails safe) | P3 | Use a trusted forwarded header, plus a test |
| 11 | `main` is 102 commits behind the release line | Technical debt | P3 | Merge the release line back to `main` (approval) |
| 12 | Interactive "Sync now" and freshness panel use a 5 s timeout, so they can fail on a cold source | Technical debt | P3 | Known since Phase 1 |
| 13 | Opportunity limit (`OPPORTUNITY_SYNC_LIMIT`, earlier observed at 200) | Technical debt | P3 | **UNVERIFIED** whether it still truncates after checkpointing. Compare counts with Lever |
| 14 | Portal feedback, document storage, automatic stage progression, Module Admin, branded portal domain, CI-driven deployment | Future | F | Not V1 |

## Completed: do not repeat

- V1 merge (#92), image builds, UAT and Production rollouts.
- Talent/Recruitment/Platform migrations (the heads are current).
- The first full reconciles (DEV, UAT, Production) and their integrity checks.
- Audit outbox setup and backlog drain.
- Resuming the Production reconcile schedule.
- The XSS fix.
- The cold-start and batching performance work.
- The 182 local security and isolation tests.
