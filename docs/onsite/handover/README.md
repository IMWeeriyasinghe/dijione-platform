# Diji On-site — Windows → Mac handover package

State verified on **2026-11-13** (≈16:00–16:30 UTC) from the Windows machine, read-only.
Nothing in Azure, the production PC, ZKBioTime or the authoritative database was changed
while preparing this package.

## Three components — never merge their responsibilities

| Name (exact) | What it is | Where the code lives |
|---|---|---|
| **Diji On-site Agent** | Windows service + WPF admin UI on the ZKBioTime PC. Reads `iclock_transaction` read-only, delivers events over HTTPS. | `DijiOnsite-Agent` repo (`src/`, `deploy/service`, `deploy/installer`, `deploy/production-pc`) |
| **Diji On-site Attendance** | The ONE shared authoritative ingestion API (Azure App Service) + Azure SQL store (`rg-diji-onsite-attendance`). | `DijiOnsite-Agent` repo (`services/DijiOnsiteAttendance.Ingestion`, `deploy/azure/attendance`, `contracts/ingestion-v1`) |
| **Diji On-site** | The DijiOne module: `onsite-api`, `onsite-web`, per-environment `onsite_<env>` mirror, Workforce Directory consumer. | This repo (`apps/onsite-api`, `apps/onsite-web`, plus registration in platform-api / shell-web / people-api) |

## Reading order

1. [MAC-AGENT-START-HERE.md](MAC-AGENT-START-HERE.md) — rules and first commands for the receiving agent
2. [PROJECT-OVERVIEW.md](PROJECT-OVERVIEW.md) — what exists, feature inventory and status
3. [SYSTEM-ARCHITECTURE.md](SYSTEM-ARCHITECTURE.md) — end-to-end data flow, read vs write, boundaries
4. [DATA-MODEL-AND-SYNC.md](DATA-MODEL-AND-SYNC.md) — schemas, EventId, mirror sync, reconciliation, verification queries
5. [FRONTEND-BACKEND.md](FRONTEND-BACKEND.md) — onsite-api routes, onsite-web pages, shared patterns
6. [IDENTITY-MATCHING.md](IDENTITY-MATCHING.md) — **the major open investigation**
7. [INFRASTRUCTURE-ENVIRONMENTS.md](INFRASTRUCTURE-ENVIRONMENTS.md) — Azure inventory, DEV/UAT/PROD, drift
8. [AGENT-OPERATIONS.md](AGENT-OPERATIONS.md) — production PC, service, checkpoint, safety rules
9. [SECURITY-AND-ACCESS.md](SECURITY-AND-ACCESS.md) — auth, permissions, identities, secrets
10. [GIT-AND-RELEASE-WORKFLOW.md](GIT-AND-RELEASE-WORKFLOW.md) — branches, release, rollback, two-machine workflow
11. [MAC-DEVELOPMENT-SETUP.md](MAC-DEVELOPMENT-SETUP.md) — toolchain and bootstrap on macOS
12. [CURRENT-STATUS-AND-BACKLOG.md](CURRENT-STATUS-AND-BACKLOG.md) — issues register, blockers, next tasks
13. [VALIDATION-CHECKLIST.md](VALIDATION-CHECKLIST.md) — how to re-verify everything above

Existing module documentation stays canonical and is referenced, not duplicated:
`docs/onsite/architecture.md`, `deployment.md`, `requirements.md`, `module-removal.md`,
`photos-pagination-drilldown.md`, `sql-principal.sql`, and `docs/platform/workforce-directory.md`.
The Agent repo has its own entry point: `docs/handover/MAC-HANDOVER.md` in `DijiOnsite-Agent`.

## Repositories and the commits this package describes

| Repo | Remote | Branch to start from | Commit |
|---|---|---|---|
| DijiOne | `https://github.com/IMWeeriyasinghe/dijione-platform` (see `git remote -v`) | `release/onsite-v1` (integration line) + `docs/onsite-handover` (this package) | release head `7eabdc6` |
| DijiOnsite-Agent | `https://github.com/IMWeeriyasinghe/DijiOnsite-Agent.git` | `main` + `docs/mac-handover` | main `d18e882` |

See [GIT-AND-RELEASE-WORKFLOW.md](GIT-AND-RELEASE-WORKFLOW.md) for exact verification commands.
