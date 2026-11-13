# PROD replica floors — Phase 1 runbook

Operational tooling for the 2026-11 Production performance decision, Phase 1. It sets
`minReplicas = 1` on six PROD Container Apps, one app at a time:

- `people-api`
- `birthday-api`
- `atwork-api`
- `atwork-web`
- `onsite-api`
- `onsite-web`

CPU, memory and maximum replicas are not touched. The template side of the same change (so a later
deployment can't revert it) lives in `deploy/bicep/main.prod.bicepparam`, `atwork-release.bicep` and
`onsite-release.bicep`. The execution record is `docs/platform/prod-replica-floor-phase1.md`.

**Do not run `apply` without an explicit, current approval for PROD (gate P1-A).**

## Commands

The `az` CLI must be signed in to the PROD subscription.

```bash
cd deploy/runbooks/prod-replica-floor
python3 phase1_runbook.py precheck                    # read-only; must print PRECHECK PASS
export PHASE1_APPROVED=yes                            # only after explicit approval
python3 phase1_runbook.py apply people-api            # then birthday-api, atwork-api, atwork-web, onsite-api, onsite-web
python3 phase1_runbook.py audit                       # read-only: where each app stands
python3 phase1_runbook.py rollback <app>              # restores minReplicas 0 (allowed at any time)
python3 measure.py before|after-t30                   # read-only HTTP measurements
```

`apply` is refused outside `PHASE1_WINDOW_UTC` (default `17:00-18:00`). `rollback` isn't restricted by the window.

## What each `apply` does

1. **Checks the live app.** It must match the recorded baseline snapshot exactly: image digest, env vars, secret references,
   probes, resources, ingress, identity and the minimum replica count.
2. **Checks that no other deployment is underway, and stops if one is.** It looks for:
   - any ARM deployment that hasn't settled;
   - any app or job in the resource group that isn't `Succeeded`;
   - any running migration or bootstrap job execution;
   - any Container Apps, Jobs, managed-environment or deployment write in the activity log in the last
     60 minutes, other than the runbook's own verified operations (below).
3. **Waits for related job executions.** It waits until **no** execution of a related job is running; any execution counts, not just the
   latest. Related means:
   - jobs that call the app directly;
   - jobs that run the app's image (its migration job);
   - indirect callers (`birthday-scan-job` → `birthday-api` → `people-api`).

   If they don't finish within 3 minutes, it stops without changing anything.
4. **Records the operation and sends the update.** It writes the operation to `ledger.json` (app, signed-in principal, start and end), then runs
   `az containerapp update -g rg-dijione-prod -n <app> --min-replicas 1`. Azure CLI 2.92 sends a PATCH with
   only `template.scale.minReplicas`. That creates one new revision with the same image digest.
5. **Waits for the new revision.** It must be the latest ready revision, `Healthy`, `Provisioned`, carry 100% of the traffic and have ≥ 1 replica.
   It then compares the whole spec with the pre-change snapshot: only `minReplicas` may differ. The spec SHA-256 values
   before and after are written to `spec-hashes.json`.
6. **Rolls back automatically on any failure** (`PHASE1_NO_AUTO_ROLLBACK=1` disables this) and exits non-zero, so the sequence stops.
   - A rejected update is reported as "not applied". Nothing changes and nothing is rolled back.
   - A client error after a change that did apply is detected and verified like a normal update.

In single revision mode the old revision keeps serving until the new one is ready. If an update fails, traffic stays
on the old revision (Microsoft Learn, *Update and deploy changes in Azure Container Apps*). A rollback is another
`--min-replicas 0` update that creates a revision with the original spec; it's verified against the pre-change snapshot.

### Own operations only

An activity-log write counts as the runbook's own only if it is all of these:

- on the app recorded in the ledger;
- by the same principal;
- inside that operation's recorded time window (−60 s / +180 s slack for log timestamps);
- the only ARM operation (correlation id) matching that window.

That correlation id is then recorded in the ledger. Everything else blocks, including:

- a second operation in the window;
- another caller;
- any other time;
- any write on an app the runbook didn't touch.

## Tests

```bash
python3 tests/run_tests.py
```

These are offline scenario tests against `tests/fake_az.py`, with synthetic fixtures and no Azure calls. They cover:

- precheck: a clean baseline, drift, and other deployments in progress;
- apply: a clean update, a slow revision, a running non-latest job execution, an indirect caller, a rejected update, a failed revision with auto-rollback, a client error after a successful change, unexpected drift, no approval, outside the window, and a repeated apply;
- rollback: after an apply, and when there is nothing to roll back;
- the own-operation rules.

## Evidence

`evidence/<date>/` holds:

- `execution-log.txt`, `spec-hashes.json` and `measurements-*.tsv` — committed;
- raw `az containerapp show` snapshots (`baseline/`, `<app>.pre|post|rollback.json`) and `ledger.json` — kept on the
  operator's machine only (`.gitignore`), because they contain internal resource IDs and configuration values.

Azure keeps the full template of every previous revision, up to 100 inactive revisions, as the authoritative before/after record.

`kql/` holds the Log Analytics queries for the 7-day baseline and the post-change checks.
