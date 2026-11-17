# CI and repository operations

How GitHub, CI and branches are run for `dijione-platform` while it is a
**private repository on GitHub Free**. The CI contract (what must run,
what may be skipped, how a skip is verified) is
[`engineering-gatekeeper.md`](engineering-gatekeeper.md) §4 and §6; this
document is the operating procedure around it.

## 1. Constraints

| Constraint | Consequence |
|---|---|
| Private repository, GitHub Free (personal account) | 2,000 hosted-runner minutes per billing cycle, shared by all private repos of the account. With a $0 budget, jobs stop starting when it is used up ("recent account payments have failed or your spending limit needs to be increased" — seen 2026-09-03). |
| No branch protection or rulesets on private Free | Nothing on GitHub blocks a bad merge. The Engineering Gatekeeper's checks are the only gate. |
| GitHub fires `schedule` triggers and reads `dependabot.yml` from the **default branch** only | Scheduled runs and Dependabot follow whatever the default branch contains. |
| Secret scanning / push protection need a paid plan on private repos | Secret detection is `gitleaks` in CI (below). |

## 2. Branch model

**Target model** — one integration branch, which is also the default branch:

- `main` is the integration branch and the default branch. Feature,
  fix and docs branches are cut from `main` and merged back by PR.
- `release/<name>` branches are cut from `main` for promotion to
  UAT/PROD and receive only targeted cherry-picks/hotfixes, as
  `release/onsite-v1` did (`release-pipeline.md`).
- Because `main` is the default branch, the weekly regression, the weekly
  full-history secret scan and Dependabot all work without extra plumbing.

**Transition (one-time, requires the owner's approval).** Since September
2026 day-to-day integration happened on `release/onsite-v1`; `main` was
left at `e21fdb2` (2026-09-03). `main` has **no commits** that
`release/onsite-v1` lacks, so it can be **fast-forwarded** to the release
head: no merge commit, no conflict, no history rewrite. Afterwards new
PRs target `main`; the open drafts into `release/onsite-v1` are retargeted
to `main` when they are next worked on. Until the transition is approved,
`release/onsite-v1` remains the integration branch, the weekly schedule
does not fire (run it manually, §4) and Dependabot keeps targeting the
stale `main` with the old workflows.

## 3. Workflows and run modes

`ci.yml` — one change-aware workflow. Gates on every event: `scope`,
`guard` (module independence + CI-scope self-tests), `ci-result`.

| Trigger | Mode | What runs | Typical billed minutes |
|---|---|---|---|
| Draft PR (opened / pushed) | draft | gates only; `ci-result` warns "not validation evidence" | ~3 |
| PR ready for review, or push to a ready PR | scoped | legs whose inputs changed (`ci-scope.js` rules) | 3–40 (depends on diff) |
| PR changing CI files (`ci.yml`, `scripts/ci/**`) | full | every leg | ~95 |
| Push to `main` (post-merge) | post-merge | gates only | ~3 |
| `workflow_dispatch`, `mode=full` | full | every leg — release-promotion regression | ~95 |
| Weekly schedule, or `workflow_dispatch` `mode=scheduled-regression` | schedule | guard + the four module-removal jobs | ~25 |

`secret-scan.yml` — `gitleaks` on every pushed commit of every branch
(the PR's check comes from this push scan), plus a weekly (Monday 03:30
UTC, default branch) and on-demand **full-history** scan.

## 4. Procedures

**Normal PR.** Open as draft while iterating (~3 min per push). Mark
ready for review when it should be validated; the Gatekeeper verifies the
`scope` summary against the diff (`engineering-gatekeeper.md` §6).

**Release promotion.** Before UAT/PROD promotion:
`gh workflow run ci.yml --ref <release-branch> -f mode=full`, wait for
green, and record the run link in the release record.

**Weekly regression without a default-branch schedule** (only while the
transition in §2 is pending): run
`gh workflow run ci.yml --ref <integration-branch> -f mode=scheduled-regression`
once a week.

**After any change to `ci.yml`, `scripts/ci/**`, `dependabot.yml` or
`secret-scan.yml`:** the PR runs in full mode; changes to schedules or
Dependabot take effect only once they reach the default branch.

## 5. Actions minutes

- Allowance: **2,000 min/cycle** (GitHub Free; confirm plan, cycle dates
  and budget on the Billing page). **Early warning: 1,500 min.**
- Check (read-only; a calculation from job durations, not GitHub's
  billing record): `node scripts/ci/actions-usage.js` (current month), or
  `--since <YYYY-MM-DD|ISO time>`. Exit code 3 at/above the threshold.
  Authoritative figure: Settings → Billing and licensing → Usage.
- Reference figures (2026-11): full run 94 min (measured); post-change
  replay of the busiest 30 days 1,558 min; private baseline 105 min
  (2026-11-17, PR #122 validation).
- At the warning threshold: keep PRs in draft until they are ready,
  batch small fixes, avoid unnecessary manual full runs, and decide
  whether to defer non-urgent work or fund extra minutes (owner decision —
  never by disabling or bypassing gates).

## 6. Security baseline

- `gitleaks` on every pushed commit + weekly full-history scan.
- `guard` (module independence) on every CI event.
- Dependabot version updates, grouped per ecosystem: npm and every Python
  service/package (`/apps/*-api`, `/packages/*-py`) monthly; Actions
  quarterly (an Actions bump forces a full CI run).
- **Dependabot alerts** (vulnerability alerts) are a repository setting,
  free on private repositories — keep them enabled.
- Workflow token permissions default to read; only `scope` gets
  `pull-requests: read`.

## 7. Account and device checks (owner)

| Check | Where / how |
|---|---|
| Plan, cycle dates, Actions budget, failed payments | GitHub → Settings → Billing and licensing |
| Mac Git access | `gh auth status`; `git push --dry-run origin HEAD` (verified 2026-11-17) |
| Windows Git access | `gh auth status`; `git credential-manager github list`; `git push --dry-run origin HEAD` |

## 8. Changing CI

Any change that narrows CI — `scripts/ci/ci-scope.js` rules, the
`CI_SCOPE_SPEC` legs/`within`/`also`/`onSchedule`, triggers, or
`ci-result`'s `needs:` — is `HUMAN_REQUIRED` (`engineering-gatekeeper.md`
§6). `node --test scripts/ci/` must pass; it runs inside `guard` too.
