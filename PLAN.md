# DijiOne Platform — Build Plan

Status: Phase 1 (First Autonomous Run) complete; Phase 2 (Identity,
Authorization, Administration) complete. See `docs/mvp-status.md` for the
full checklist and quality-gate results of both phases.
Authoritative contract: [CLAUDE.md](./CLAUDE.md), extended by the DijiOne
Phase 2 change request (identity/authorization/Admin Center).

## Repository state at start

Repository was blank except `CLAUDE.md` and `.claude/settings.json`. No git
history existed. This plan documents the bootstrap from zero.

## Architecture decision

Modular monolith per CLAUDE.md §6:

- `apps/web` — one Next.js 15 App Router application hosting the DijiOne
  shell and all module UIs (including DijiTalentFlow).
- `apps/api` — one FastAPI application exposing platform + module APIs.
- `modules/talent-flow` — DijiTalentFlow domain documentation/fixtures owned
  by the module; actual route/service code lives inside `apps/web` and
  `apps/api` under module-scoped folders to avoid Next/FastAPI multi-package
  build complexity during the MVP, per §8 "may adapt exact folder placement
  to framework constraints".
- `packages/*` — shared TS types/config used by `apps/web` (documented, not
  a separate publishable package during MVP — see ADR 0001).
- `integrations/*` — provider adapter documentation; actual adapter code
  lives in `apps/api/app/integrations/{lever,hubspot}` since FastAPI cannot
  import across a JS workspace boundary. Directories are kept as documented
  extension points per repository structure guidance.

## Phases

- [x] Phase 0 — Planning, repo inspection, docs skeleton
- [x] Phase 1 — DijiOne platform foundation (Next.js shell, FastAPI, SQLite,
      Alembic, design tokens, module registry, dev identity)
- [x] Phase 2 — DijiTalentFlow core (Client + TA workspaces, domain model,
      demo data)
- [x] Phase 3 — Workflow & security (CS review state, notifications, audit
      log, tenant isolation tests)
- [x] Phase 4 — Mock integration architecture (LeverClient, HubSpotClient,
      ExternalMapping, IntegrationEvent, webhooks)
- [x] Phase 5 — 55-65% review point / quality gates (lint, build, pytest,
      ruff, migrations) — see `docs/mvp-status.md` for full results
- [ ] Phase 6+ — Live discovery / production hardening — NOT started; blocked
      on credentials by design, not a blocker for this run.

## Phase 2 — Identity, Authorization & Admin Center

- [x] Centralized `AuthorizationService` + Role/Permission/RolePermission
      catalog (`app/core/permissions.py`, single source of truth for the
      Alembic backfill and `scripts/seed.py`).
- [x] Client/portfolio scope (`UserModuleClientScope`) replacing the
      "one client or all clients" limitation with an explicit portfolio.
- [x] `SUPER_ADMIN` platform role + lockout/admin-role-change protection.
- [x] DijiOne Admin Center: backend (`/api/admin/*`) + frontend
      (`/admin/*`, 8 pages).
- [x] Module assignment `enabled` flag; `User` Phase 2 identity fields
      (`entra_object_id`, `identity_provider`, `last_login_at`).
- [x] Microsoft Entra ID OIDC integration seam extended
      (`/api/auth/entra/*`) — not activated, fails fast with 501 until
      real tenant credentials exist.
- [x] Admin audit logging (reuses existing `AuditLog`, no new store).
- [x] Regression: all 18 Phase 1 tests still pass unmodified; 17 new
      Phase 2 tests added (`test_authorization_phase2.py`,
      `test_admin_center.py`).
- [x] Docs: `docs/platform/authorization.md`, `docs/platform/admin-center.md`
      (new); `authentication.md`, `module-framework.md`, `architecture.md`
      updated.

See `docs/mvp-status.md` for the full Definition-of-MVP-Done checklist and
`docs/decisions/0001-monorepo-layout.md` for the repository-layout ADR
referenced below.

## Notes

- No production credentials available or requested. Mock providers only.
- SQLite for local dev, PostgreSQL-compatible schema via SQLAlchemy 2.
- Dev Identity Mode replaces Entra ID locally; seam documented in
  `docs/platform/authentication.md`. Phase 2 kept this seam intact —
  Dev Identity Mode and the target Entra ID flow both resolve through the
  same `AuthorizationService`, only identity acquisition differs.
