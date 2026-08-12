# DijiOne Admin Center

See also: [`docs/diagrams/rendered/13-admin-center-flow.png`](../diagrams/rendered/13-admin-center-flow.png) (source: [`docs/diagrams/source/13-admin-center-flow.mmd`](../diagrams/source/13-admin-center-flow.mmd)).

The Admin Center is a privileged platform module within DijiOne — not a
separate product — visible only to users whose resolved
`platform_permissions` include `platform.admin.access` (SUPER_ADMIN or
PLATFORM_ADMIN). It inherits the DijiOne design system (warm red/orange
gradient sidebar, cream active state, white cards) so it feels like a
natural part of the platform, not a bolted-on backoffice tool.

## Navigation

```text
Administration
├── Dashboard        /admin              user/module/admin counts, pending review count
├── Users            /admin/users        every DijiOne identity
│   └── User Detail  /admin/users/[id]   status, platform role, module access, effective access
├── Applications      /admin/applications module registry (DijiTalentFlow/Birthday/Spark)
├── Roles             /admin/roles        role catalog with permission/user counts
├── Permissions       /admin/permissions  permission catalog, grouped by module + category
├── Client Access     /admin/client-access staff client/portfolio scope, all in one place
└── Audit             /admin/audit         every administrative change
```

`AdminLayout` (`apps/web/src/app/admin/layout.tsx`) gates the whole
subtree with `usePlatformAdmin()` — a non-admin persona sees an empty-state
explaining why, with a link back to DijiOne Home, never a broken page.
Every admin screen keeps a persistent "Back to DijiOne Home" footer link
(CR §36).

## Backend enforcement

The frontend gate above is a UX convenience only. Every `/api/admin/*`
route independently depends on `require_platform_admin` at minimum;
mutating routes additionally depend on `require_platform_permission(...)`
for the specific action (`platform.admin.manage_users`,
`platform.admin.manage_admins` implicitly via `AdminService`'s own check,
`platform.admin.view_audit`). See `docs/platform/authorization.md`.

## User Detail / Access screen

Matches CR §26: status toggle, platform role selector, and one editor card
per registered module (`ModuleAssignmentEditor` in
`app/admin/users/[id]/page.tsx`) with:

- **Enabled** checkbox — disabling immediately removes the module from that
  user's DijiOne Home ("My Apps") on their next request, enforced
  server-side by `GET /api/modules` filtering on `UserModuleRole.enabled`.
- **Role** select — populated from `GET /api/admin/roles` filtered to that
  module, so an administrator picks "Talent Acquisition Member" rather than
  typing `TA_MEMBER` (CR §49 — no raw permission strings required).
- **Client Scope** — "All Clients" checkbox, or a checkbox list of specific
  clients (CR §22/§30 portfolio scope), backed by
  `PUT /api/admin/users/{id}/modules/{module_key}`.

Modules with no roles defined yet (DijiBirthday, DijiSpark) render as a
read-only card explaining that no functional roles exist yet — CR §4.2/4.3
explicitly forbid building functional workflows for these modules in this
phase, so their assignment editor is intentionally inert rather than fake.

## Effective Access view

`GET /api/admin/users/{id}/effective-access` resolves — not just
displays — the user's actual permission set per module plus their platform
permissions, using the same `AuthorizationService` the API itself uses for
every request. This guarantees the Effective Access panel can never show
something the backend wouldn't actually enforce (CR §31).

## SUPER_ADMIN lockout & admin-role protection (CR §50)

Enforced in `AdminService`, independent of any frontend check:

- deactivating or demoting the **last** active SUPER_ADMIN is rejected
  (403) with a clear message;
- granting/revoking SUPER_ADMIN or PLATFORM_ADMIN requires the caller to
  already hold `platform.admin.manage_admins` (SUPER_ADMIN only) — a
  PLATFORM_ADMIN attempting this receives 403.

Covered by `tests/test_admin_center.py`.

## Audit

`/admin/audit` reads the same `AuditLog` table every business workflow
already writes to (talent request created/reviewed, etc.), filtered/sorted
by recency. Every admin mutation appends actor, action, entity, and
before/after JSON state — no separate admin-only audit store was
introduced (CR §41 — "do not create redundant parallel authorization
systems").

## What is intentionally not built in this phase

- Role/permission **creation or deletion** UI — the catalog is seeded and
  system-protected (`Role.is_system=True`); CR §28 allows this to come
  later "if it can be done safely within this phase," and extending an
   already-large schema change with a full role editor was judged out of
  scope for the MVP window (CLAUDE.md §8 — scope discipline).
- Per-client-per-staff-user restriction below the module-role level beyond
  what `UserModuleClientScope` already provides.
- DijiBirthday / DijiSpark functional administration — placeholders only.
