# PROD replica floors — Phase 1 execution record (2026-11)

Record of the first increment of the 2026-11 Production performance decision (target Option B,
applied incrementally). Tooling: `deploy/runbooks/prod-replica-floor/`. Template change: PR #97
(`chore/deploy-prod-replica-floor` → `release/onsite-v1`).

## Scope

The six PROD Container Apps below move to one warm replica (`minReplicas` 0 → 1). Values are
min / max replicas.

| App | Before | After | Why |
|---|---|---|---|
| `people-api` | 0 / 2 | 1 / 2 | Diji On-site Workforce Directory reloads hit a freshly started replica (23 of 23 in 7 days) |
| `birthday-api` | 0 / 2 | 1 / 2 | 473–495 cold starts a week, driven by the 10-minute `birthday-comms-job` |
| `atwork-api` | 0 / 1 | 1 / 1 | Cold API call took 23.3 s; the 15-minute notifications job keeps waking it |
| `atwork-web` | 0 / 1 | 1 / 1 | Opening DijiAtWork cold took 18.65 s |
| `onsite-api` | 0 / 1 | 1 / 1 | Always up because of the 1-minute sync, but billed at the active rate |
| `onsite-web` | 0 / 1 | 1 / 1 | Opening Diji On-site after idle waited about 15 s |

What stays the same:
- CPU (0.25 vCPU), memory (0.5Gi) and maximum replicas.
- The Workforce Directory cache TTL (600 s).
- DEV and UAT, PostgreSQL and application code.

## Approvals

- **P1-B (Git):** approved 2026-11-13. Local commit, push of `chore/deploy-prod-replica-floor`, and draft PR #97. Merging needs separate approval after the initial Production validation.
- **P1-A (Production):** approved 2026-11-13 for the six services, in the 17:00–18:00 UTC window. The same day the user explicitly moved it to the daytime window; the lower-traffic window was a precaution, not a technical dependency.
  - The session-scheduled run was cancelled to prevent a duplicate execution.
  - The runbook ran with `PHASE1_WINDOW_UTC=05:55-07:30`. The code default (17:00–18:00) is unchanged.
  - The guard was verified before use: the default window refused the time, the deployment window allowed it, and the offline suite passed 21/21.

## Pre-execution validation (2026-11-13)

**Templates.**
- `az bicep build`, `build-params` and `lint` pass with 0 warnings.
- The compiled ARM JSON differs from the `75a9a3d` baseline only in the replica-floor values.
- ARM what-if (read-only) shows `minReplicas 0 → 1` on the four Diji On-site and DijiAtWork apps in PROD, and no scale change in UAT or DEV.

**Mechanism.**
- In DEV's revision history, 38 revisions were created by `minReplicas`-only changes, and `minReplicas` was the only field that changed.
- In earlier switchovers the old revision stayed active until the new one was ready, about 20–36 s.
- Azure CLI 2.92 sends `{"properties":{"template":{"revisionSuffix":null,"scale":{"minReplicas":N}}}}`.

**Runbook.** 21 of 21 offline scenarios pass (`tests/run_tests.py`).

**Live precheck (read-only) at 05:21 UTC: PASS.**
- All six apps match the recorded baseline across the full spec.
- No ARM deployment was running, every app and job was `Succeeded`, no migration was running, and there were no foreign writes in the last 60 minutes.

**Platform events (last 7 days).**
- Key Vault fetch and "context canceled" errors were seen once, on 2026-11-08 at 01:52 UTC, across several apps in the same second. This was a one-off platform blip with no recurrence.

**Known, unrelated.**
- On PR #97, the `birthday-api` test `test_detection_defaults_delivery_date_to_birthday_occurrence` fails on the run date because "today + 9 days" falls on a weekend.
- The recorded 2026-11-02 PROD `onsite-release.bicep` parameters are stale (older image digests and the sync schedule `0 */6 * * *`). Any re-run must pass the live values.

## Execution (2026-11-13, 06:02–06:29 UTC)

**Final live precheck at 05:59:59 UTC: PASS.**
- All six apps matched the recorded baseline across the full spec.
- No other deployment was underway, and no related job was running.

Each update was applied individually and verified before the next one. Every `apply` passed first time: **no rollback and no stop condition**.

| App | Revision before → after | min | Spec SHA-256 (before = after) | Applied |
|---|---|---|---|---|
| `people-api` | `--0000003` → `--0000004` | 0 → 1 | `19be23287c2d` | 06:03–06:04, 75 s |
| `birthday-api` | `--0000005` → `--0000006` | 0 → 1 | `69ba0e31aa86` | 06:07–06:08, 67 s |
| `atwork-api` | `--tjl96gz` → `--0000001` | 0 → 1 | `e8f95fc35fa2` | 06:12–06:13, 77 s |
| `atwork-web` | `--zu0g4z2` → `--0000001` | 0 → 1 | `c27a1edfc43a` | 06:18–06:19, 60 s |
| `onsite-api` | `--0000004` → `--0000005` | 0 → 1 | `f1d9bb3fed3a` | 06:23–06:24, 75 s |
| `onsite-web` | `--0000003` → `--0000004` | 0 → 1 | `2a0b9cd716d0` | 06:28–06:29, 73 s |

Each new revision ended up:
- Healthy and Provisioned, with 1 replica and 100% of the traffic;
- the only active revision;
- running the same image digest;
- with a spec hash identical before and after, so image, env, secrets, probes, resources, ingress and identity are unchanged.

The full log is in `deploy/runbooks/prod-replica-floor/evidence/2026-11-13/run/` (`execution-log.txt` and `spec-hashes.json`).

Verification after each app:
- **Replicas:** Running and ready, 0 restarts.
- **Gateway:** one request returned the same HTTP status as before.
- **Jobs on the new revisions:** the `birthday-comms-job` 06:10 run, the `atwork-notifications-job` 06:15 run and the `people-workforce-sync-job` 06:15 run all Succeeded.
- **`onsite-api` handover:**
  - The job guard waited for the running 06:23 sync to finish before updating.
  - The 06:23:18 sync was served by `--0000004` and every run from 06:24:20 by `--0000005`, with no gap.
  - All five syncs after the update Succeeded, with no abandoned or failed run.
- **Own operations:** the activity-log exclusion ignored only the runbook's own recorded operations: 2, 4, 6, 8 and 10 events at successive steps, each with its correlation id recorded in the ledger.
- **Rest of PROD:** the floor check after the run shows every other PROD app unchanged.

**Stability after the change (06:02–06:31 UTC):**
- All 42 job executions Succeeded, including 29 `onsite-sync-job` runs.
- All six apps had 0 restarts.
- There were no scale-from-zero activations on the six apps.
- There were no Key Vault errors or terminations.
- `atwork-api` logged `ProbeFailed` 5 times: 3 isolated 1-second probe timeouts, at 06:15:45, 06:21:15 and 06:23:45.
  - They were never consecutive. A restart needs 4 consecutive liveness failures, and removal from service needs 6 consecutive readiness failures.
  - `/health` is a static handler with no database or dependency call.
  - This is the same pre-existing pattern as `onsite-api`, which had 19 in the previous 24 h while always on. It's monitored; tuning the default 1-second probe timeout is a Phase 2 item.

## Measurements

The probes are unauthenticated read-only GETs through `https://dijione.dijitalteam.com`. "Before" was taken at 05:59–06:02 UTC. "After" was taken at 06:41 UTC, following an idle gap of at least 10 minutes on the measured endpoints; under the old configuration the apps would have scaled to zero by then. The raw samples are in `evidence/2026-11-13/measurements-*.tsv`.

Server time is time to first byte minus the TCP and TLS handshake, so it is roughly the server time plus one round trip.

| Target | Serving app | First request before | First request after | Warm p50, before → after |
|---|---|---|---|---|
| DijiAtWork Home card `/api/atwork/summary` | `atwork-api` | **23.84 s** (cold) | **0.27 s** | 229 → 102 ms |
| DijiBirthday Home card `/api/birthday/summary` | `birthday-api` | **27.17 s** (cold) | **0.28 s** | 272 → 262 ms |
| Open DijiAtWork `/atwork` | `atwork-web` | **22.36 s** (cold) | **0.11 s** | 98 → 238 ms |
| Open Diji On-site `/onsite` | `onsite-web` | **20.71 s** (cold) | **0.26 s** | 93 → 250 ms |
| Diji On-site Home card | `onsite-api` (already always on) | 0.11 s | 0.25 s | 242 → 247 ms |
| Home `/`, `/api/auth/me` (control, already warm) | `shell-web`, `platform-api` | 0.23 / 0.26 s | 0.09 / 0.28 s | 250 / 91 → 84 / 244 ms |
| Controls left at 0: talent card, `/talent-flow`, `/admin` | `talent-api`, `talent-web`, `admin-web` | 26.1 / 14.2 / 20.2 s | 28.7 / 14.1 / 20.4 s | — |

How to read the figures:
- **Cold starts are eliminated** on the four affected entry points.
- **The controls stayed cold**, which confirms the improvement comes from the replica floors.
- **Warm medians** split between about 90 ms and about 250 ms in both runs. That follows the client's two network paths (TCP connect about 70 ms or about 240 ms, as found in the investigation), not the server.

Pending:
- **T+24 h:** `kql/post-change.kql`, covering scale churn, probe failures and restarts, On-site sync health, and cold Workforce Directory reloads (target 0).
- **The 7-day cost observation**, per app per day. Thresholds: ≤ AUD 0.45/day for each warm app, and ≤ AUD 0.66/day for `onsite-api`.

Cost figures in this record are **forecasts** until they are observed in billing.
