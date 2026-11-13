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
- **P1-A (Production):** approved 2026-11-13 for the six services, in the 17:00–18:00 UTC window.

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

## Execution

_Pending: to be completed after the 17:00–18:00 UTC window on 2026-11-13._

## Measurements

_Pending: before (shortly before the window), T+30 min, T+24 h, and the 7-day cost observation._

Cost figures in this record are **forecasts** until they are observed in billing.
