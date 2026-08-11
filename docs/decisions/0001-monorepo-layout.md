# ADR 0001: Monorepo layout — code-boundary vs directory-boundary modules

Status: Accepted (Phase 0 of the first autonomous run)

## Context

CLAUDE.md §7 suggests a repository structure with top-level `modules/`,
`packages/`, and `integrations/` directories alongside `apps/web` and
`apps/api`, but also says explicitly: "the implementation may adapt exact
folder placement to framework constraints, but the architectural
boundaries must remain clear."

Next.js (App Router) and FastAPI each expect their own conventional
project layout (`apps/web/src/app/**`, `apps/api/app/**`). Physically
splitting DijiTalentFlow's frontend into `modules/talent-flow` and
importing it into `apps/web` would require a JS workspace/package setup
(pnpm/turborepo workspaces or path aliases) for a single-module MVP, and
FastAPI cannot import Python from a directory tree separate from `apps/api`
without an equivalent package split on the Python side.

## Decision

Keep one Next.js app and one FastAPI app. Enforce module boundaries by
**naming convention and route/role scoping**, not by directory-per-module:

- Frontend: `apps/web/src/app/talent-flow/**` (routes),
  `apps/web/src/components/talent/**` (module-specific components).
- Backend: `apps/api/app/api/routes/talent_*.py`,
  `apps/api/app/services/*_service.py` scoped to `talent_request`,
  `application`, etc., all gated through `module_key="talent-flow"` in
  `UserModuleRole` and `ApplicationModule`.
- `modules/`, `packages/`, `integrations/` top-level directories are kept
  as empty documented placeholders is **not** done — instead, their intent
  is captured here and in `docs/platform/module-framework.md`, so a future
  module (or a future extraction of DijiTalentFlow into its own service)
  has a documented seam to follow, without dead scaffolding directories
  sitting empty in the repo.

## Consequences

- Adding a second real module (DijiBirthday) follows the pattern
  documented in `docs/platform/module-framework.md` §"Adding a new
  module" — no repository restructuring required.
- Extracting DijiTalentFlow into an independently deployed service later
  is still possible: its backend code only depends on `app/core`,
  `app/db`, and its own `talent_*` files, and its frontend code only
  depends on `components/ui`, `components/shell`, and `lib/*` — both of
  which are the *shared platform* layer this ADR keeps in place.
- If DijiOne grows to 4-5+ modules with different release cadences or
  teams, revisit this decision — a real workspace split (pnpm workspaces +
  a shared `packages/ui`) becomes worth the overhead at that scale, but
  would be premature complexity for a one-module MVP (CLAUDE.md §8).
