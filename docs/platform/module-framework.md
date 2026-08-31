# DijiOne Module Framework

## Module registry

`ApplicationModule` (table `application_modules`, owned by `platform-api`)
is the single source of truth for which modules exist and are visible:

```text
id, key, name, description, icon, route, status, enabled,
display_order, required_roles, created_at, updated_at
```

- `key` — stable identifier (`talent-flow`, `birthday`, `spark`), never
  renamed once shipped.
- `status` — `ACTIVE` or `COMING_SOON` (DijiBirthday/DijiSpark are seeded as
  `COMING_SOON` so the registry — and the Home page's "My Apps" grid — can
  demonstrate multi-module growth without half-built module UIs). This is
  the module's **product status** — distinct from a service's **runtime
  status** (is it actually reachable right now); see
  `docs/platform/failure-isolation.md` "Module status vs runtime status".
- `required_roles` — non-empty string means "the user needs some role
  within this `module_key`"; empty means visible to any authenticated user.

`GET /api/modules` (served by `platform-api`) filters the registry against
the caller's `UserModuleRole` rows before returning it, so a user only ever
sees modules they're authorized to open (CLAUDE.md §9/§10). A module row
is only counted as "authorized" when the assignment is also
`enabled=true` — a platform administrator disabling one user's
DijiTalentFlow access (via the Admin Center) removes it from that user's
DijiOne Home immediately, without touching the module registry itself.

**Phase 2.6**: "authorized" here still means the module's row appears in
`GET /api/modules`; it does not itself change with Access Groups (module
registry visibility isn't group-aware). What *is* group-aware is the *role*
that DijiOne Home shows next to a module card — `ModuleCard.tsx` reads it
from `user.module_roles` in the resolved auth session, which (since
`claims_service.build_claims` now calls
`AuthorizationService.effective_module_roles`) already reflects group-
granted roles, not only direct assignment. See
`docs/platform/authorization.md` "Access Groups (Phase 2.6)".

## Source domains are not modules

`recruitment-api`, `people-api`, and `commercial-api` are **not** in
`ApplicationModule` and never will be — they have no `GET /api/modules`
row, no Home card, no `required_roles`, and no user-facing UI at all. A
source domain exists solely to own one external provider integration and
publish a canonical read model over HTTP to the application services that
need it (`docs/platform/service-architecture.md` "Source domains vs
application domains", `docs/platform/data-ownership.md`). Do not register a
source domain in the module registry, and do not add module-registry
plumbing (icons, routes, role gates) to one — that machinery is for
products a user opens, not for an internal integration owner.

## Adding a new module (a new service, not new routes)

Pre-Phase-2.5, a new module meant adding routes to the shared monolith.
Since the application-level service split, a new *real* module (one with
actual business logic, past the skeleton stage) means standing up its own
backend service and, if it needs dedicated UI beyond a Home card, its own
frontend app — following the pattern `apps/birthday-api` and
`apps/spark-api` already establish:

1. **Backend service**: scaffold `apps/<module>-api/` with the same shape
   every other backend service has — `app/main.py`, `app/core/config.py`,
   `app/api/routes/health.py` (`GET /health`), and
   `app/api/routes/<module>.py` with at minimum `GET /api/<module>/metadata`
   and `GET /api/<module>/summary` (CR §9/§10/§18). Add domain models,
   repositories, services, and its own database
   (`sqlite:///./<module>.db` locally) only once there's real business data
   to store — `birthday-api`/`spark-api` deliberately have none yet.
2. **Auth seam**: wire `packages/auth-client-py`'s claims decode
   (`app/api/deps.py`, `make_get_claims(...)`) exactly as `talent-api`
   and the two skeleton services do — no database join, no synchronous
   call to `platform-api`. See `docs/platform/authorization.md` "Claims-
   based authorization for business services".
3. **Roles & permissions**: extend `apps/platform-api/app/core/permissions.py`'s
   catalog (`ALL_ROLES`/`ALL_PERMISSIONS`) with the module's role/permission
   set — this still lives in `platform-api` since it owns the Role/
   Permission catalog tables and computes the claims every business service
   reads. No other service's authorization code needs to change.
4. **Registry**: insert an `ApplicationModule` row (via
   `apps/platform-api/scripts/seed.py` or a migration) with
   `status="ACTIVE"` once the module is ready, and add its
   `key -> /api/<module>/summary` mapping to
   `apps/shell-web/src/components/home/ModuleCard.tsx`'s
   `MODULE_SUMMARY_PATH` so its Home card shows a live runtime-status badge.
5. **Frontend** (only if the module needs dedicated screens beyond a Home
   card): scaffold `apps/<module>-web/` as its own Next.js zone —
   `basePath: "/<module-key>"`, `transpilePackages` for
   `@dijione/design-system`/`@dijione/auth-client`/`@dijione/contracts`,
   and rewrites in `apps/shell-web/next.config.ts` proxying both its pages
   and its backend's API prefix. Reuse `@dijione/design-system` — do not
   fork the design system per module. See
   `docs/platform/service-contracts.md` "Gateway / routing" for the exact
   pattern and its cross-zone-navigation gotcha.
6. **Docs**: add `docs/<module>/requirements.md`, update this file's module
   table below, and add the service to
   `docs/platform/service-architecture.md`'s service table and
   `docs/platform/local-development.md`'s port table.

## Current modules

| Key           | Name           | Status      | Backend | Frontend | Notes |
|----------------|----------------|-------------|---------|----------|-------|
| `talent-flow`  | DijiTalentFlow | ACTIVE      | `talent-api` :8002 | `talent-web` :3002 | First major module — see `docs/talent-flow/*`. |
| `birthday`     | DijiBirthday   | ACTIVE      | `birthday-api` :8003 | `birthday-web` :3003 | Automated birthday-cake ordering (BambooHR detection, idempotent orders, dashboard/upcoming/orders register/order detail, supplier management, Microsoft Graph email send) — V1 (Phases A–D) complete; see `docs/birthday/requirements.md`. Supplier portal (F), automated reply-capture (E/G), and Cowork hooks (H) are later phases. |
| `spark`        | DijiSpark      | COMING_SOON | `spark-api` :8004 (skeleton) | none yet | Health/metadata/summary + auth seam only; no business logic (CR §10). |

## Design-system inheritance

Modules do not define their own color tokens, typography, or primitive
components. Every frontend app imports UI primitives and shell chrome from
`@dijione/design-system` (`packages/design-system/src/ui/*`,
`packages/design-system/src/shell/*`) and the CSS custom properties defined
in `packages/design-system/src/globals.css` (`--dt-*` tokens — see
`docs/platform/design-system.md`), copied into each app's own
`src/app/globals.css` with a Tailwind v4 `@source` directive so the shared
package's class names still get generated (Tailwind's automatic content
detection doesn't reliably reach into a sibling workspace package). A
module may add narrow accent variations (e.g. a module-specific icon in the
sidebar header) but must not introduce a competing visual identity
(CLAUDE.md §52).
