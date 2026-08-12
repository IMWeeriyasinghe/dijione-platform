# DijiOne Module Framework

## Module registry

`ApplicationModule` (table `application_modules`) is the single source of
truth for which modules exist and are visible:

```text
id, key, name, description, icon, route, status, enabled,
display_order, required_roles, created_at, updated_at
```

- `key` — stable identifier (`talent-flow`, `birthday`, `spark`), never
  renamed once shipped.
- `status` — `ACTIVE` or `COMING_SOON` (DijiBirthday/DijiSpark are seeded as
  `COMING_SOON` so the registry — and the Home page's "My Apps" grid — can
  demonstrate multi-module growth without half-built module UIs).
- `required_roles` — non-empty string means "the user needs some role
  within this `module_key`"; empty means visible to any authenticated user.

`GET /api/modules` filters the registry against the caller's
`UserModuleRole` rows before returning it, so a user only ever sees modules
they're authorized to open (CLAUDE.md §9/§10). Since Phase 2, a module row
is only counted as "authorized" when the assignment is also
`enabled=true` — a platform administrator disabling one user's
DijiTalentFlow access (via the Admin Center) removes it from that user's
DijiOne Home immediately, without touching the module registry itself.

## Adding a new module (e.g. DijiBirthday)

1. **Backend**: add `app/models/<module>_*.py` domain models, a
   `repositories/`, `services/`, `schemas/`, and `api/routes/<module>_*.py`
   set following the `talent_*` naming convention. Register routers in
   `app/main.py`.
2. **Roles**: extend `app/core/constants.py` with the module's role enum
   (e.g. `HR_USER`, `HR_ADMIN`) and reuse `UserModuleRole.module_key`. Add
   the role and its permissions to `app/core/permissions.py`'s catalog
   (`ALL_ROLES`) so the Admin Center's role/permission editors and
   `AuthorizationService` pick it up automatically — no other authorization
   code needs to change (see `docs/platform/authorization.md`).
3. **Registry**: insert an `ApplicationModule` row (via a migration or the
   seed script) with `status="ACTIVE"` once the module is ready.
4. **Frontend**: add `apps/web/src/app/<module-key>/` with its own
   `layout.tsx` (role-aware sidebar, same `AppShell` primitive) and pages.
   Reuse `components/ui/*` — do not fork the design system per module.
5. **Docs**: add `docs/<module>/requirements.md` and update this file's
   module table below.

## Current modules

| Key           | Name           | Status      | Notes |
|----------------|----------------|-------------|-------|
| `talent-flow`  | DijiTalentFlow | ACTIVE      | First major module — see `docs/talent-flow/*`. |
| `birthday`     | DijiBirthday   | COMING_SOON | Registry entry only; no UI built yet. |
| `spark`        | DijiSpark      | COMING_SOON | Registry entry only; no UI built yet. |

## Design-system inheritance

Modules do not define their own color tokens, typography, or primitive
components. They import from `apps/web/src/components/ui/*` and the CSS
custom properties defined in `apps/web/src/app/globals.css`
(`--dt-*` tokens — see `docs/platform/design-system.md`). A module may add
narrow accent variations (e.g. a module-specific icon in the sidebar
header) but must not introduce a competing visual identity
(CLAUDE.md §52).
