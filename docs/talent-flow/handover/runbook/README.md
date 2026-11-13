# V1 rollout runbook (reference copies)

These are copies of the scripts used for the DEV, UAT and Production V1 rollouts on 10–12 November 2026. They lived in a temporary folder on Windows and were never in the repository.
- **They contain no secrets.** They reference Key Vault secret *names* only.
- **They are not runnable as they stand.** They expect the helpers in a sibling `audit-runbook/` folder and write state to `audit-runbook/state-<env>/`. Their Windows Git Bash details (`cygpath`, `MSYS_NO_PATHCONV`) need adjusting for macOS.
- **Never run them without explicit owner approval** for the specific environment and phase.

| File | Purpose |
|---|---|
| `deploy_talentflow_uat.sh` / `deploy_talentflow_prod.sh` | Phased rollout: `pre lock build suspend audit-job platform recruitment talent web audit-verify sync reconcile drain` (Production adds `talent-finish`; `build` there imports by digest) |
| `deploy_audit_dev.sh` | DEV rollout of the audit outbox, and the first full reconcile |
| `jobcheck.py` | Verifies `talent-audit-outbox-job` against its approved configuration (`RB_ENV`, `RB_REGISTRY`) |
| `cfgcmp.py`, `cmdfix_diff.py` | Strict before/after configuration comparison |
| `gate.py` | Evaluates a gate expression over JSON snapshots |
| `imgverify.py` | Verifies an API image file by file against a commit |
| `c2_body_*.py` | Inline bodies for one-off job executions: `snap` (read-only integrity snapshot, counts and hashes only), `fresh` (source freshness), `rehearsal` (reconcile in a rolled-back transaction), `run` (one real reconcile), `probe` |

The procedure and its lessons are in [../05-OPERATIONS-AND-OPEN-ITEMS.md](../05-OPERATIONS-AND-OPEN-ITEMS.md).
