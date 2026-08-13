# DijiOne Platform — Build Plan

Status: Phase 1 (First Autonomous Run) complete; Phase 2 (Identity,
Authorization, Administration) complete; Phase 2.5 (Application-Level
Service Separation) complete; Phase 2.6 (Enterprise Access Management +
Intelligent Home) complete. See `docs/mvp-status.md` for the full
checklist and quality-gate results of all four phases.
Authoritative contract: [CLAUDE.md](./CLAUDE.md), extended by the DijiOne
Phase 2 change request (identity/authorization/Admin Center), the
Phase 2.5 change request (service separation — see
`docs/platform/service-architecture.md`), and the Phase 2.6 change request
(access groups + effective access + Home redesign — see
`docs/platform/access-groups.md`).

## Repository state at start

Repository was blank except `CLAUDE.md` and `.claude/settings.json`. No git
history existed. This plan documents the bootstrap from zero.

## Architecture decision (superseded by Phase 2.5 — see below)

The layout below was the Phase 1/2 architecture. Phase 2.5 replaced it with
eight application-level services; this section is kept as the historical
record of the starting point the ADR at `docs/decisions/0001-monorepo-
layout.md` and the Phase 2.5 change request both explicitly designed
around. Current architecture: `docs/platform/service-architecture.md`.

Modular monolith per CLAUDE.md §6 (Phase 1/2, no longer current):

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

## Phase 2.5 — Application-Level Service Separation

- [x] `platform-api` extracted: owns identity, authorization, module
      registry, audit log, notifications; issues JWTs with signed
      authorization claims.
- [x] `packages/auth-client-py` built: claims verification +
      `PlatformClient` HTTP wrapper shared by every business service.
- [x] `admin-api` extracted as a zero-database service — forwards to
      `platform-api` with the caller's own bearer token, enriched from
      `talent-api`.
- [x] `talent-api` extracted: owns its own database, authorizes from
      claims, audit/notification writes are best-effort HTTP calls.
- [x] `birthday-api` / `spark-api` skeletons: health/metadata/summary +
      the same claims-based auth seam, no business logic.
- [x] `packages/design-system`, `packages/auth-client-ts`,
      `packages/contracts` extracted from `apps/web`; `shell-web`,
      `admin-web`, `talent-web` split out as independent Next.js zones
      behind `shell-web`'s gateway.
- [x] Root npm workspace + `npm run dev:all` starts all eight services.
- [x] `apps/web` and `apps/api` deleted after extraction was verified.
- [x] Regression: 74 backend tests + 6 package tests, all frontend apps
      build/lint clean, live browser smoke test including a real
      `talent-api` outage/recovery cycle.
- [x] Docs: `docs/platform/service-architecture.md`,
      `service-contracts.md`, `failure-isolation.md`,
      `local-development.md` (new); `architecture.md`, `authorization.md`,
      `admin-center.md`, `module-framework.md`, `authentication.md`,
      `mvp-status.md`, this file (updated).
- [x] Diagrams: service architecture, service boundaries, gateway
      routing, data ownership, failure isolation, local dev topology,
      future Azure deployment.

## Phase 2.6 — Enterprise Access Management + Intelligent Home

- [x] `AccessGroup` / `UserGroupMembership` / `GroupModuleRole` /
      `GroupModuleClientScope` models (`apps/platform-api/app/models/access_group.py`),
      additive alongside the existing direct-assignment tables; new Alembic
      migration.
- [x] `AuthorizationService` extended with `groups_for_user`,
      `effective_module_roles`, `effective_client_scope`,
      `effective_permissions` — additive-ALLOW resolution (union of direct +
      active-group grants; ALL_CLIENTS overrides a concrete-client-list
      contributor). Single resolution engine: `AdminService.effective_access`
      and `claims_service.build_claims` both consume these same methods.
- [x] `AdminService` group CRUD + `application_detail` (app-centric admin
      view); SYSTEM-type groups protected from deactivation.
- [x] New routes: `apps/platform-api/app/api/routes/platform_admin.py`
      (`/groups/*`, `/applications/{module_key}`) and mirrored pass-through
      routes in `apps/admin-api/app/api/routes/admin.py`.
- [x] New TS contracts in `packages/contracts/src/types.ts`
      (`AccessGroupOut`, `AccessGroupDetailOut`, `AccessSourceOut`,
      `ApplicationDetailOut`, extended `EffectiveModuleAccessOut`).
- [x] `admin-web`: new Groups list/detail screens, new Applications detail
      screen, User Detail refactored into six tabs (Overview / Applications
      / Groups / Client Access / Effective Access / Audit History) with
      `sources`-based DIRECT/INHERITED-FROM badges, Users list search +
      client-side filters, new "Groups" nav item.
- [x] `shell-web`: Home reordered (Header → My Apps → Needs Your Attention
      → Recent Activity + Platform Health + Ask DijiOne), new
      `AttentionPanel.tsx` and `PlatformHealth` components (role-aware,
      real-data-only, isolated per-service fetches), `ModuleCard.tsx` shows
      operational summary fields + resolved role per app, COMING_SOON
      modules visually de-emphasized.
- [x] Regression: 40 new `platform-api` tests + 12 new `admin-api` tests,
      all passing alongside the full pre-2.6 suite; both frontend apps build
      clean.
- [x] Docs: `docs/platform/access-groups.md`, `docs/platform/effective-access.md`
      (new); `authorization.md`, `admin-center.md`, `module-framework.md`,
      `service-architecture.md`, `mvp-status.md`, this file (updated).

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
