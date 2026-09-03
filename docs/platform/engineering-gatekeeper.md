# DijiOne Engineering Gatekeeper

> **Authoritative pull-request, CI verification, merge, and post-merge operating contract for DijiOne.**
>
> This document defines the boundary between the Development Agent and the Engineering Gatekeeper.
>
> The Gatekeeper exists to remove routine CI review, failure diagnosis, PR verification, and merge administration from the user while preserving GitHub-enforced quality and safety controls.

**GATEKEEPER MODE: AUTO**

This line is the single source of truth for the Gatekeeper's operating mode. See §8 for the full mechanism. Any agent acting as the Engineering Gatekeeper MUST read this line before taking any action on any pull request.

---

# 1. PURPOSE

The DijiOne Engineering Gatekeeper is an independent verification and delivery-control role.

The normal engineering workflow is:

```text
User Requirement
      ↓
Development Agent
      ↓
Implementation
      ↓
Tests / Local Verification
      ↓
Commit / Push
      ↓
Pull Request
      ↓
GitHub CI
      ↓
Engineering Gatekeeper
      ├── FAIL → diagnose → return precise finding to Development Agent
      │                         ↓
      │                       fix
      │                         ↓
      │                       CI again
      │
      └── PASS → final Gatekeeper verification
                            ↓
                         MERGE
                            ↓
                    Post-merge validation
                            ↓
                         COMPLETE
```

---

# 2. ROLES & BOUNDARIES

## Development Agent (`.claude/agents/dev-agent.md`)

Owns:

- implementation, bug fixes, refactoring;
- tests and migrations;
- `.env.example` sync for any new `Settings` field;
- local verification (ruff, pytest, alembic upgrade head, npm lint, npm build)
  before every push;
- branch/commit preparation and PR creation/updates;
- correcting defects the Gatekeeper returns.

The Development Agent's own successful local verification is never final
approval for merge. It never merges its own PR, never edits branch
protection, and never force-pushes.

## Engineering Gatekeeper (`.claude/agents/gatekeeper.md`)

Owns:

- independent PR verification — it re-derives evidence itself and never
  accepts the Development Agent's claim that "tests pass" at face value;
- GitHub CI/check inspection (`gh pr checks`, `gh run view --log-failed`);
- failed-check diagnosis and classification (§5);
- the architecture/security/migration gate (§6), beyond "CI green";
- precise, evidence-backed defect handoff to the Development Agent (§3);
- re-verification after fixes;
- merge eligibility and — in `AUTO` mode — the merge itself (§4, §8);
- post-merge verification;
- safe source-branch deletion after a successful merge;
- human escalation (§7) instead of acting, whenever a trigger applies.

The Gatekeeper has no `Write`/`Edit` tool. Even a trivial CI-configuration
fix goes back to the Development Agent as a finding — this keeps the
Development Agent the sole code-writer and the audit trail unambiguous.

## Both agents

Both `.claude/agents/*.md` definitions treat this document as their source
of truth and reference it rather than duplicating its content. If this
document and an agent's own file ever disagree, this document governs.

---

# 3. HANDOFF PROTOCOL

State lives entirely in GitHub — PR comments and check-runs — not in a
separate database. Re-running the Gatekeeper against a PR is simply
re-reading the PR's comment history and current check state, which is
idempotent and auditable. Both blocks below are posted via `gh pr comment`.

## DEV HANDOFF (Development Agent → Gatekeeper)

```markdown
## DEV HANDOFF
**PR:** #<number> — <title>
**Branch:** <feat|fix|chore|docs>/<slug> → main
**Services touched:** <e.g. platform-api, talent-api>
**Change summary:** <1-3 sentences>
**Local gates run:** ruff [pass/fail] · pytest [pass/fail] · alembic upgrade head [pass/fail] · npm lint [pass/fail] · npm build [pass/fail]
**Migrations:** none | <files>, downgrade reversible: yes/no
**Provider boundary changes:** none | <describe>
**.env.example sync:** n/a | done
**Ready for Gatekeeper verification.**
```

## GATEKEEPER RESPONSE (Gatekeeper → Development Agent / PR)

```markdown
## GATEKEEPER RESPONSE
**PR:** #<number>
**Verdict:** PASS_ALL_GATES / FIX_REQUIRED / HUMAN_REQUIRED
**CI status:** <required check name> pass/fail/pending — one line per required context
**Findings:** (empty if PASS_ALL_GATES)
1. **Category:** <one of the §5 categories>
   **Job/check:** <e.g. pg (talent-api)>
   **Evidence:** <exact log excerpt / assertion / file:line>
   **Required fix:** <precise, actionable instruction>
2. ...
**Architecture/security/migration gate:** PASS / FAIL — <detail if FAIL>
**Action:** <one of the following>
  - returning to Development Agent for fixes
  - MERGED (mode = AUTO)
  - READY_TO_MERGE — awaiting manual merge (SHADOW MODE, decision N of 2)
  - escalating to human (see HUMAN ESCALATION REQUIRED below)
```

## HUMAN ESCALATION REQUIRED (Gatekeeper → user)

```markdown
## HUMAN ESCALATION REQUIRED
**PR:** #<number>
**Trigger:** <one of the §7 categories>
**Why this needs you:** <specific reason>
**What I will NOT do without your sign-off:** <the blocked action>
**Recommendation:** <Gatekeeper's suggested path, if any>
```

---

# 4. GITHUB ENFORCEMENT CONFIGURATION

**CURRENT STATUS: NOT CONFIGURED — GitHub plan limitation.** This
repository is private on the GitHub Free plan. Both the classic branch
protection API and the newer rulesets API were checked directly
(`gh api repos/.../branches/main/protection`, `gh api
repos/.../rulesets`) and both return `403 Upgrade to GitHub Pro or make
this repository public to enable this feature` — confirmed on
2026-09-01. **Neither is available on a private repo below GitHub Pro.**

The user has decided to proceed without GitHub-native branch protection
for now, rather than upgrade the plan or make the repo public. This is a
deliberate, known gap, not an oversight: **until this changes, the
Engineering Gatekeeper's own verification is the sole safety layer.**
There is no GitHub-side backstop that refuses a bad merge, blocks a
force-push, or stops the repo owner from bypassing the process — if the
Gatekeeper's judgment is wrong, or someone pushes to `main` directly
outside the agreed workflow, nothing on the GitHub side stops it. Every
role in this document should weigh that when deciding how conservatively
to act — in particular, `HUMAN_REQUIRED` calls in §7 matter more, not
less, with no server-side enforcement layer underneath them, and the
Gatekeeper should treat ambiguity as a reason to escalate rather than
proceed.

**Revisit when the plan allows it.** If the repository is later upgraded
to GitHub Pro (or moved to a Team/Enterprise-owned org), apply the
configuration below via a one-time `gh api
repos/IMWeeriyasinghe/dijione-platform/branches/main/protection` PUT
(a repo-admin-level write — user-run or user-reviewed single agent
action, never something the Gatekeeper redoes per PR), and update this
section's status line accordingly. Until then, treat everything below as
the target configuration, not the current state.

GitHub, once this is configured, becomes the hard enforcement layer. The
Gatekeeper adds intelligent verification on top of it and must never
bypass it:

- `required_status_checks.strict = true` — the branch must be up to date
  with `main` before merge.
- `required_status_checks.contexts` — the exact per-matrix-leg check names
  as GitHub renders them, `<job> (<matrix-value>)`:
  - `lint-test`: platform-api, admin-api, talent-api, recruitment-api,
    people-api, commercial-api, birthday-api, spark-api (8)
  - `upgrade`: platform-api, talent-api, recruitment-api, people-api,
    commercial-api, birthday-api (6)
  - `pg`: platform-api, talent-api, recruitment-api, people-api,
    commercial-api, birthday-api (6)
  - `lint-build`: shell-web, admin-web, talent-web, talentflow-portal-web,
    birthday-web, birthday-supplier-web (6)
  - `gitleaks` (1)
  - **27 named contexts total.**
- `enforce_admins = true` — protection applies even to the repo owner.
  CODEOWNERS names only the human user themselves, so without this the
  "no bypass" guarantee has a hole.
- `required_pull_request_reviews = null` — no required-approval review.
  CODEOWNERS is solely the repo owner and GitHub blocks self-approval, so
  the gate is required status checks + the Gatekeeper's own independent
  audit, not a review requirement.
- `allow_force_pushes = false`, `allow_deletions = false`.
- `required_conversation_resolution = true` — also gives a natural signal
  once the Gatekeeper starts posting findings as PR comments: are its own
  threads cleared before merge.
- `required_linear_history` — left at GitHub's default (off).
- Repo setting `allow_auto_merge` — left **disabled**. The Gatekeeper polls
  (`gh pr checks --watch`) and merges itself rather than handing the
  decision to GitHub's built-in auto-merge queue, because that queue only
  knows about required status checks, not the architecture/security/
  migration/guard-test-actually-ran checks in §6. GitHub's required checks
  remain the hard server-side enforcement layer regardless of who clicks
  merge.

**Known brittleness.** GitHub has no wildcard/regex support for required
status-check contexts, so the 26-context list above drifts whenever a
workflow matrix changes (this has already happened once — `commercial-api`
was added to CI in Wave H). Any PR that touches a matrix in
`.github/workflows/*.yml` without an accompanying required-context update
is a `CI_CONFIGURATION_DEFECT` finding (§5). Once branch protection is
actually configured, the Gatekeeper checks this by comparing the current
workflow matrices against a `GET` of the live branch protection settings;
**while it remains unconfigured (current status, above), the Gatekeeper
instead treats this document's 26-context list as the source of truth for
"every required check" and must independently confirm all 26 ran and
passed via `gh pr checks` on every PR** — there is no GitHub-side list to
defer to.

**Who applies this, once available.** The initial `PUT` is a one-time,
user-run (or user-reviewed single agent action) step — not something the
Gatekeeper redoes per PR. The Gatekeeper only ever performs a `GET`
against this endpoint, to confirm the baseline hasn't drifted (§7). While
unconfigured, this `GET`/drift-check is not applicable — skip it, don't
treat the absence of protection itself as a per-PR finding (it's already
the documented, decided current state, not a surprise).

---

# 5. FAILURE CLASSIFICATION

On any failed required check, the Gatekeeper reads `gh pr checks` for the
failing context, then `gh run view <run-id> --log-failed`, and classifies
into exactly one category:

`CODE_DEFECT` · `TEST_DEFECT` · `MIGRATION_DEFECT` · `POSTGRES_DEFECT` ·
`DEPENDENCY_DEFECT` · `FRONTEND_BUILD_DEFECT` · `LINT_DEFECT` ·
`TYPE_CONTRACT_DEFECT` · `SECURITY_DEFECT` · `ARCHITECTURE_DEFECT` ·
`CI_CONFIGURATION_DEFECT` · `ENVIRONMENT_DEFECT` · `FLAKY_TEST` ·
`EXTERNAL_SERVICE_FAILURE` · `UNKNOWN`

| Signal | Category |
|---|---|
| `lint-test (<service>)`, `ruff check .` step fails | `LINT_DEFECT` |
| `lint-test (<service>)`, pytest step fails on application code | `CODE_DEFECT` |
| `lint-test (<service>)`, pytest step fails because the test itself is wrong | `TEST_DEFECT` |
| Failure in `apps/recruitment-api/tests/test_lever_client_safety.py`, `apps/talent-api/tests/test_no_direct_lever_dependency.py`, or `apps/birthday-api/tests/test_no_direct_bamboohr_dependency.py` | `ARCHITECTURE_DEFECT` — see the FIX_REQUIRED vs. HUMAN_REQUIRED rule immediately below |
| `upgrade (<service>)` (SQLite) fails | `MIGRATION_DEFECT` |
| `pg (<service>)` fails on upgrade/downgrade with a Postgres-specific error that does not reproduce on SQLite (real precedent: commit `edf46d5`) | `POSTGRES_DEFECT` |
| `pg (<service>)` downgrade step fails with something other than the expected "no reversible chain" fallback | `MIGRATION_DEFECT` — also check whether `downgrade()` intentionally `raise NotImplementedError` (expected, two precedents already in the repo) vs. an unexpected exception (real defect) |
| `pip install -r requirements.txt` / resolver conflict | `DEPENDENCY_DEFECT` |
| `lint-build (<app>)`, ESLint/TSC error | `LINT_DEFECT` / `TYPE_CONTRACT_DEFECT` (TS type errors specifically) |
| `lint-build (<app>)`, Next.js build failure | `FRONTEND_BUILD_DEFECT` |
| `gitleaks` finding | `SECURITY_DEFECT` — if the finding looks like a real (non-placeholder) credential, also trigger human escalation for rotation regardless of whether the PR itself gets cleaned |
| No app-level log content, runner/infra error (e.g. `actions/checkout` failure, timeout) | `ENVIRONMENT_DEFECT` |
| Same commit flips pass/fail across a re-run | `FLAKY_TEST` — re-run once via `gh run rerun --failed` before concluding; never auto-merge on a lucky green; report the flake and require the Development Agent to fix determinism or explicitly justify it |
| Failure indicates a real external Lever/BambooHR/HubSpot call when `INTEGRATIONS_MODE` should be `mock` | `EXTERNAL_SERVICE_FAILURE` |
| Unmatched after one classification attempt | `UNKNOWN` — report full raw evidence rather than guess; two consecutive `UNKNOWN`s on the same PR is itself worth flagging to the user (the classifier is failing, not just the PR) |

## Architecture guard-test failures: FIX_REQUIRED vs. HUMAN_REQUIRED

A guard-test failure is always classified `ARCHITECTURE_DEFECT`, but that
classification does **not** by itself mean human escalation:

- **Default: `FIX_REQUIRED`.** If the failure is an accidental
  implementation defect — e.g. a stray direct import of a provider client
  outside its owning service — the Gatekeeper returns the exact defect to
  the Development Agent. If the Development Agent restores the
  already-approved architecture (removes the disallowed dependency) and the
  guard test passes again, the Gatekeeper independently re-verifies the
  corrected diff and the PR continues normally. No human involvement is
  required for a defect that gets corrected back into compliance.
- **`HUMAN_REQUIRED`** applies only when the proposed resolution would
  *intentionally* change, weaken, remove, or bypass an approved
  architecture/security/provider-ownership boundary — e.g. widening a
  guard test's allowlist, keeping a direct cross-service dependency on
  purpose, or the required correction cannot be made without such a
  change. This is the same rule as §7's "architecture-approved-change
  conflicts" trigger.
- **Any proposed live Lever write capability is `HUMAN_REQUIRED`
  immediately**, under the LIVE LEVER SAFETY CONTRACT (CLAUDE.md §60),
  regardless of how the guard-test path plays out. See §6.3.

---

# 6. ARCHITECTURE / SECURITY / MIGRATION GATE

"All required checks passed" is necessary but not sufficient. Before any
`PASS_ALL_GATES` verdict, the Gatekeeper independently re-derives:

1. **Guard tests actually ran, not skipped.** For any PR touching
   `talent-api`, `recruitment-api`, or `birthday-api` application code,
   confirm the relevant guard test's `PASSED` line is present in the job
   log — not absent via a stray `-k` filter or `@pytest.mark.skip`. A
   guard test that ran and failed follows the FIX_REQUIRED/HUMAN_REQUIRED
   rule in §5. A guard test that silently did not run at all is itself a
   finding (`CI_CONFIGURATION_DEFECT` or `ARCHITECTURE_DEFECT` depending on
   whether it looks accidental or deliberate) — unless the PR also modified
   the guard test's own skip/allowlist logic, in which case treat it as
   the intentional-weakening case in §5/§7 (`HUMAN_REQUIRED`).

   **Matrix-level `skipped` conclusion — verify against the diff, don't
   trust it blindly.** `api.yml`, `migrations.yml`, `postgres.yml`, and
   `web.yml` each run a `detect` job (`dorny/paths-filter@v3`) ahead of
   their matrix job, and gate each matrix leg with
   `if: needs.detect.outputs[matrix.<key>] == 'true'`. A leg that doesn't
   run reports `conclusion: skipped` in `gh pr checks` / the check-runs
   API — this is architecturally identical to a workflow that never
   triggered at all (§4's existing not-triggered-is-not-a-defect rule),
   but is **not** automatically acceptable the same way. Before treating
   any `skipped` matrix leg as legitimate, the Gatekeeper MUST:
   - pull the actual PR diff (`gh pr diff` or the compare API) and confirm
     the skipped service/app's own directory, and every shared path its
     `detect` filter also watches (e.g. `packages/auth-client-py/**` for
     api/postgres legs, `packages/**` + root lockfiles for web legs), is
     genuinely absent from the changed-files list;
   - for a `packages/**` or shared-dependency change, confirm **no**
     consumer leg is skipped — a skip on a fan-out-eligible service/app
     when a shared dependency changed is a `CI_CONFIGURATION_DEFECT`
     (the filter didn't fan out correctly), not a legitimate skip;
   - treat a `skipped` leg whose component the diff *does* touch as a
     `CI_CONFIGURATION_DEFECT` (the `detect` job's filter is wrong or
     stale) and route it to the Development Agent like any other
     configuration defect, not silently accept it as `PASS`.
   A verified-legitimate skip carries no further weight — it is treated
   exactly like a not-triggered workflow (informational, not a gate
   failure). An unverified skip must never be waved through.
2. **New cross-service DB/FK reference.** `gh pr diff` scanned for a new
   import of another service's SQLAlchemy models, or a new engine/session
   pointed at another service's `DATABASE_URL` env var — violates the "no
   cross-service DB access, no cross-service joins" rule in CLAUDE.md's
   Data Ownership appendix. → `ARCHITECTURE_DEFECT`, handled per §5's
   FIX_REQUIRED/HUMAN_REQUIRED split.
3. **New Lever write-verb usage.** `gh pr diff` grepped for `.post(`,
   `.put(`, `.patch(`, `.delete(`, or a new `create_/update_/delete_/
   archive_/move_` method under `apps/recruitment-api/app/integrations/
   lever/` (or the equivalent live-client path). Defense-in-depth on top
   of the guard tests — **any hit is an automatic `HUMAN_REQUIRED`**, never
   just a returned finding, per the LIVE LEVER SAFETY CONTRACT's "STOP and
   report for explicit user authorization."
4. **Secret/tracked-file hygiene beyond gitleaks.** `gh pr diff` checked
   for any staged `apps/*/.env` (not `.env.example`), `*.db`/`*.sqlite*`,
   or key-material file (`*.pem`, `*.key`, `*.pfx`, `*.p12`,
   `serviceAccount*.json`) — CONTRIBUTING.md's own "never commit" list,
   a file-type/tracking-status concern gitleaks' content-pattern scanning
   would not necessarily catch.
5. **Destructive/irreversible migrations.** For every changed/added file
   under `apps/*/alembic/versions/`, check `downgrade()`:
   - a newly introduced `raise NotImplementedError` → `HUMAN_REQUIRED`
     (unless the same pattern already existed in that file before this
     PR);
   - `op.drop_table`/`op.drop_column` reversing a change made by an
     *earlier* migration (not this file's own `upgrade()`) → flag as
     destructive, requires explicit human sign-off;
   - no `downgrade()` at all, or a bare `pass` → `MIGRATION_DEFECT`
     (incomplete migration), routed to the Development Agent, not an
     escalation.

---

# 7. HUMAN ESCALATION TRIGGERS

| Trigger | Concrete signal in this repo |
|---|---|
| Destructive/irreversible migration | §6.5 |
| Production deployment / Azure provisioning / material cloud-cost change | Any new `infra/`/`deploy/` path, or a workflow `deploy` job (none exist today — `docs/platform/pre-cloud-handoff.md` confirms nothing is provisioned) |
| Entra tenant/app-registration change / DNS change | Diff touching Entra/Graph integration config beyond the documented dev-identity stub |
| Secret/credential rotation | A real (non-placeholder) `gitleaks` finding |
| Permission-model / security-boundary redesign | Diff changing `platform-api`'s additive-ALLOW-only Access Group semantics, or introducing a DENY construct |
| Architecture-approved-change conflicts | Diff contradicting `docs/platform/data-ownership.md`'s ownership table, or the "architecture is CLOSED unless..." clause in CLAUDE.md; also the intentional-weakening branch of §5/§6.1 |
| Enabling write access to a currently read-only provider | §6.3 (Lever), and the equivalent check for BambooHR writes |
| Bypassing GitHub protection / required checks | Once branch protection is configured: the Gatekeeper's own `gh api .../branches/main/protection` `GET` returns settings drifted from the configured baseline in §4 — report the drift, never silently re-apply it (re-applying is itself a protection write the Gatekeeper is not permitted to make). **Currently (protection not configured, §4): treat any attempt to merge without every one of the 26 required checks having actually run and passed as this same trigger** — there is no GitHub-side backstop, so the Gatekeeper's own check is the only thing standing in for it |
| Emergency merge with failing/skipped required checks | Refuse; always escalate rather than use `gh pr merge --admin` |
| Major dependency upgrade with material compatibility risk | A Dependabot PR outside the pre-scoped `npm-minor-patch`/`pip-minor-patch` groups — i.e. a semver-major bump |
| Anything the Gatekeeper cannot confidently classify | Two consecutive `UNKNOWN` classifications on the same PR (§5) |

---

# 8. MODE SWITCH & ROLLBACK

The `**GATEKEEPER MODE: ...**` line near the top of this document is the
single mechanism for both the rollout gate and the rollback kill switch.
The Gatekeeper reads it before acting on any PR. Three valid values:

- **`SHADOW`** (starting mode, immediately after the bootstrap PR merges).
  The Gatekeeper runs the complete verification loop — CI polling,
  classification, findings, re-verification, the §6 gate — and posts a
  full `GATEKEEPER RESPONSE`. When the verdict is `PASS_ALL_GATES`, it does
  **not** call `gh pr merge`; it reports `READY_TO_MERGE` and stops,
  incrementing a visible counter on this same line, e.g.
  `**GATEKEEPER MODE: SHADOW (decisions: 1/2)**`. The user merges manually
  each time and judges whether the decision was correct.
- **`AUTO`.** Identical verification; on `PASS_ALL_GATES` the Gatekeeper
  executes the merge itself (`gh pr merge`, no `--admin`, no `--force`)
  and proceeds to post-merge validation (§9's live-rollout checklist).
- **`DISABLED`** (kill switch). The Gatekeeper may still inspect and
  comment, but must not report `PASS_ALL_GATES` as actionable and must
  never merge. Every PR waits for a human regardless of CI state.

**The `SHADOW` → `AUTO` transition is a one-line, user-made edit**, not
something the Gatekeeper decides for itself. Once the user has compared
both of the first 2 shadow decisions against their own judgment and
confirms both were correct, the user (or the Gatekeeper, only when the
user explicitly instructs "switch to AUTO" in that moment) edits this line
to `**GATEKEEPER MODE: AUTO**`. The Gatekeeper must never self-promote from
`SHADOW` to `AUTO` based on its own assessment of its two decisions.

**Rollback.** Branch protection on `main` (§4) stays on regardless of this
document's mode — it is the permanent, independent safety net. To disable
the Gatekeeper's merge authority immediately, set this line to
`**GATEKEEPER MODE: DISABLED**` — no file deletion needed. If a `gh` token
compromise or misuse is specifically suspected (a harder stop than pausing
the agent), run `gh auth logout` or revoke the OAuth grant from GitHub
account settings.

---

# 9. TESTING STRATEGY

Run on a disposable scratch branch off `main`, before trusting the
Gatekeeper with real work:

1. Trivial docs-only green-path change — confirms end-to-end wiring:
   `gh pr merge` and branch deletion actually work with the account's
   token scope.
2. Deliberate `ruff` failure → confirms `LINT_DEFECT` classification and
   the fix round-trip.
3. Deliberate pytest assertion failure → confirms the `CODE_DEFECT` /
   `TEST_DEFECT` distinction.
4. Deliberately broken `alembic upgrade head` → confirms `MIGRATION_DEFECT`,
   distinct from a Postgres-only failure.
5. A change that passes SQLite but fails Postgres → confirms
   `POSTGRES_DEFECT` distinction.
6. (a) A disallowed import that trips `test_no_direct_lever_dependency.py`,
   fixed by simply removing the import → confirms normal `FIX_REQUIRED`
   handling, not escalation, once the Development Agent restores
   compliance and the Gatekeeper re-verifies.
   (b) The same guard failure "fixed" instead by widening the guard's
   allowlist, and separately a `.post(` added to the Lever client →
   confirms both are `HUMAN_REQUIRED`, blocking merge even if CI is later
   made green.
7. A migration with a newly introduced `raise NotImplementedError`
   downgrade → confirms escalation fires before merge, not after.

**Then, still before full trust:** the first 2 real (non-scratch)
development PRs after the bootstrap PR run with `GATEKEEPER MODE: SHADOW`.
The Gatekeeper posts complete `GATEKEEPER RESPONSE`s including
`READY_TO_MERGE` where applicable, but the user performs the actual merge
each time and compares it against the Gatekeeper's verdict. Only after the
user confirms both were correct does the mode line flip to `AUTO` (§8).

- [ ] Case 1 run and confirmed
- [ ] Case 2 run and confirmed
- [ ] Case 3 run and confirmed
- [ ] Case 4 run and confirmed
- [ ] Case 5 run and confirmed
- [ ] Case 6a run and confirmed
- [ ] Case 6b run and confirmed
- [ ] Case 7 run and confirmed
- [x] Shadow decision 1/2 recorded and confirmed correct — PR #35, `PASS_ALL_GATES`, manually merged 2026-09-01T07:53:18Z
- [x] Shadow decision 2/2 recorded and confirmed correct — PR #36, `PASS_ALL_GATES`, manually merged 2026-09-01T08:26:23Z
- [x] Mode switched to `AUTO` — user-authorized transition, this PR