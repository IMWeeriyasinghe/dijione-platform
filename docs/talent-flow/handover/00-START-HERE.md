# DijiTalentFlow: Windows to Mac handover (start here)

**What this is:** an agent-to-agent handover, so DijiTalentFlow development can continue on a MacBook Air M4.
- **Mac repository:** `/Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform`, already copied from the Windows repository at `C:\Projects\Diji Projects\DijiOne\dijione-platform`.
- **Verified:** 13 November 2026, about 05:30 UTC, using read-only Git and Azure checks plus one read-only query per database.
- **Not a change:** nothing in code, data or Azure was altered.
- **Scope:** TalentFlow and its direct dependencies only (Platform identity and clients, Recruitment/Lever, the portal).

## Reading order

| # | File | Contents |
|---|---|---|
| 1 | [01-CURRENT-BASELINE.md](01-CURRENT-BASELINE.md) | Exact Git state, which version to continue from, the DEV/UAT/Production comparison, Windows-only changes |
| 2 | [02-APPLICATION-AND-ARCHITECTURE.md](02-APPLICATION-AND-ARCHITECTURE.md) | Business workflows, services, source files, data, Lever, reconciliation, security; five Mermaid diagrams |
| 3 | [03-MAC-ENVIRONMENT-SETUP.md](03-MAC-ENVIRONMENT-SETUP.md) | Apple Silicon setup, local run, targeted tests |
| 4 | [04-GIT-AND-MIGRATION-PLAN.md](04-GIT-AND-MIGRATION-PLAN.md) | Validating the Mac copy, moving Windows-only items, cross-device Git rules |
| 5 | [05-OPERATIONS-AND-OPEN-ITEMS.md](05-OPERATIONS-AND-OPEN-ITEMS.md) | Deployment procedure and lessons learned, decisions, open items, what not to repeat |
| 6 | [06-MAC-CLAUDE-BOOTSTRAP.md](06-MAC-CLAUDE-BOOTSTRAP.md) | **Copy-paste prompt** for the new Claude Code session, plus read-only verification commands |
| – | [runbook/](runbook/README.md) | Reference copies of the V1 rollout scripts (previously only on Windows) |

**Authoritative sources stay in the repository:**
- `CLAUDE.md`: the contract. Its later "Data Ownership" section overrides the early monolith text.
- `docs/platform/engineering-gatekeeper.md`: PR and merge policy.
- `docs/talent-flow/v1-release-record.md`: on PR #93's branch.

## DijiTalentFlow in brief

DijiTalentFlow is the first business module of **DijiOne**. It gives Talent Acquisition staff one view of every client's recruitment.
- **Source:** **Lever**, read only.
- **Client link:** a posting belongs to a client only when it carries exactly one `DTC - <Client Name>` tag matching a known client.
- **Promotion:** verified postings become Talent Requests, and their candidacies become Candidates and Applications.
- **Sharing:** everything starts **hidden**. TA staff choose which candidates to share.
- **Client access:** clients have no accounts. A revocable, time-limited link opens a separate read-only portal showing only their own requests and shared candidates.

## Current release

- **V1** is `0437a89` (PR #92), in UAT and Production since 12 November 2026.
- **Production reconcile:** every 6 hours. The runs on 12 Nov at 18:15 and 13 Nov at 00:15 UTC succeeded.
- **DEV and UAT reconcile:** suspended.
- **Platform:** a later, separate **DijiAtWork release** (`88b9c08`/`75a9a3d`) replaced `platform-api` in all three environments and made AtWork ACTIVE. TalentFlow's own images are unchanged since V1.
- **Latest code:** `origin/release/onsite-v1` @ `75a9a3d`. **Continue TalentFlow work from there.** Never from `main`, which is 102 commits behind.

## Critical information for the incoming agent

1. **Production has one active client access link (Access4).** It was issued at 04:49 UTC on 13 Nov, redeemed once, and is not revoked. **It conflicts with the hold on client links until live-user acceptance.** Ask the owner; do not revoke it on your own. See [05, open item 1](05-OPERATIONS-AND-OPEN-ITEMS.md#open-items).
2. **Live-user acceptance has not happened.** Security behaviour is covered by automated tests only.
3. **Start in read-only mode.** Get approval for: installs, repository edits, commits, pushes, merges, Git cleanup, cloud access, job executions, migrations, Lever syncs, reconciles, access links and deployments.
4. **Lever is GET-only.** Never write to Lever, HubSpot or BambooHR.
5. **Never run tests against a hosted database.** Run `unset DATABASE_URL` first; the test fixtures drop tables.
6. **Never print or copy secrets** (`.env` files, Key Vault values) **or candidate data.** Report counts only.
7. **GitHub is the only point of synchronisation.** Compare commit hashes. Never force-push or hard-reset over unpushed work.
