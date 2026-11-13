# 06: Mac Claude Code bootstrap

[Start](00-START-HERE.md) · prev [05](05-OPERATIONS-AND-OPEN-ITEMS.md)

Paste the prompt below into a new Claude Code session started in `/Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform`.

## Before starting the agent: get the handover onto the Mac (you, in Terminal)

The handover is on GitHub, branch `docs/talentflow-handover`, with a pull request to `release/onsite-v1`. These steps **do not touch** your current branch or uncommitted files:

```bash
cd "/Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform"
git status -sb                                  # note your branch and local changes; nothing below alters them
git fetch origin docs/talentflow-handover release/onsite-v1
git worktree add .worktrees/handover-mac origin/docs/talentflow-handover   # read-only copy, detached (no branch switch)
ls .worktrees/handover-mac/docs/talent-flow/handover                      # 00-06 + runbook/
grep -q "^.worktrees/" .git/info/exclude || echo ".worktrees/" >> .git/info/exclude   # keep it out of git status
```

**If `git worktree add` complains** (for example, because of broken Windows worktree metadata), skip it. The agent can read every file straight from Git without checking anything out: `git show origin/docs/talentflow-handover:docs/talent-flow/handover/00-START-HERE.md`.

Then start Claude Code in the repository root (`claude`) and paste the prompt below.

## Copy-paste prompt

```text
You are taking over DijiTalentFlow development on my MacBook Air M4 (Apple Silicon).
The DijiOne monorepo is already copied to:
  /Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform
Do NOT clone it again.

You are in READ-ONLY ONBOARDING MODE until I approve a plan. In this mode you must NOT:
install or upgrade anything; edit, create or delete repository files; commit, push, merge,
rebase, reset, stash, prune worktrees or delete branches; run migrations, seed scripts
against anything but local SQLite, Lever syncs or reconciles; start, update, suspend or
resume any Azure resource or job (including one-off job executions); issue, extend or revoke
access links; deploy. Allowed: reading files, `git status/log/branch/worktree list/diff/
fetch --all --prune`, `command -v`/version checks, and read-only `az ... show/list` if I am
already logged in. Never print secrets, .env contents or candidate personal data.

Steps:
1. Read the handover package. It is at .worktrees/handover-mac/docs/talent-flow/handover/
   (a detached worktree of origin/docs/talentflow-handover). If that folder is missing, read
   it straight from Git with `git show origin/docs/talentflow-handover:docs/talent-flow/handover/<file>`
   (after `git fetch origin docs/talentflow-handover`). Read 00-START-HERE.md first, then
   every file it links (01-06, runbook/README.md). Do not switch the main checkout's branch.
2. Read CLAUDE.md (note: its later "Data Ownership" section overrides the early monolith text),
   docs/platform/engineering-gatekeeper.md, docs/talent-flow/v1-release-record.md (PR #93 branch)
   and docs/talent-flow/v1-uat-deployment.md.
3. Inspect the repo: current branch, uncommitted changes, stashes, worktrees (Windows paths will
   appear missing; report, don't prune), remotes, local-only commits, line-ending/file-mode noise.
4. `git fetch --all --prune`, then compare: origin/release/onsite-v1 tip vs the documented 75a9a3d;
   V1 release 0437a89; PR #93 merge state; any newer commits; whether TalentFlow paths changed
   since 0437a89 (apps/talent-api, apps/talent-web, apps/talentflow-portal-web, apps/recruitment-api).
5. State clearly: latest available code, approved development baseline, latest deployed version,
   and local-only work - and which branch new work should start from.
6. If `az` is installed and logged in to "Dijital Team IT Production", verify DEV/UAT/Production
   with the read-only commands in 06-MAC-CLAUDE-BOOTSTRAP.md and compare with 01-CURRENT-BASELINE.md.
   Do not run database probes (they start job executions) - list them as proposed actions.
7. Check Mac tooling: git, Homebrew, Python 3.12, Node 20/npm, gh, az + containerapp extension,
   Docker (optional), Claude Code; and whether .venv / node_modules are Windows leftovers.
8. Verify the architecture against code: the files named in 02-APPLICATION-AND-ARCHITECTURE.md exist,
   the retired create routes still return 403, Lever client is GET-only, reconcile/visibility/grant
   logic matches the description. Report any mismatch.
9. Explain back to me, briefly, the business workflow (Lever -> DTC mapping -> requests/candidates
   -> hidden by default -> TA sharing -> access link -> portal) and the technical architecture.
10. List completed work that must not be repeated and the open items (05, "Open items"), flagging
    item 1 (active Production Access4 link) for my decision.
11. Produce a MIGRATION READINESS REPORT: repo state, baseline, environment comparison
    (VERIFIED/UNVERIFIED), missing tools, missing Windows-only items, risks, and a numbered
    setup + synchronization plan where every action is marked as needing my approval.
Then stop and wait for my approval.

After I approve the plan, work only on what I approved: install tools, build the local environment,
then develop on new branches from origin/release/onsite-v1 as described in
04-GIT-AND-MIGRATION-PLAN.md. Ask again before any push, PR merge, Azure change, job, migration,
Lever sync, reconcile, access-link action or deployment.
```

## Read-only verification commands

```bash
# Git
git fetch --all --prune && git log --oneline -5 origin/release/onsite-v1
git merge-base --is-ancestor 0b55ccb origin/release/onsite-v1 && echo "PR93 merged" || echo "PR93 not merged"

# Azure (read-only)
az account show --query name -o tsv
for e in dev uat prod; do echo "== $e"
  az containerapp list -g rg-dijione-$e --query "[?contains(name,'talent')||contains(name,'recruitment')||name=='platform-api'||name=='shell-web'].{app:name,image:properties.template.containers[0].image}" -o table
  az containerapp job list -g rg-dijione-$e --query "[?contains(name,'talent')||contains(name,'recruitment')].{job:name,trigger:properties.configuration.triggerType,cron:properties.configuration.scheduleTriggerConfig.cronExpression,state:properties.runningStatus}" -o table
done
az containerapp job execution list -g rg-dijione-prod -n talent-reconcile-job --query "[0:4].{run:name,status:properties.status,start:properties.startTime}" -o table
az containerapp job execution list -g rg-dijione-prod -n talent-audit-outbox-job --query "[0:6].properties.status" -o tsv
# map a digest to its build tag (commit):
az acr manifest list-metadata -r crdijioneprod -n dijione/talent-api --query "[?starts_with(digest,'sha256:afee5561')].tags" -o tsv
```

**Database heads, counts and access-link state** can only be read by a one-off job execution: read-only SQL, results through Log Analytics. That starts a container, so **propose it and wait for approval**. The approach is in [05](05-OPERATIONS-AND-OPEN-ITEMS.md#lessons-learned-and-constraints), and an example body is `runbook/c2_body_snap.py`.
