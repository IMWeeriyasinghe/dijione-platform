# DijiOne Admin Center

See also: [`docs/diagrams/rendered/13-admin-center-flow.png`](../diagrams/rendered/13-admin-center-flow.png) (source: [`docs/diagrams/source/13-admin-center-flow.mmd`](../diagrams/source/13-admin-center-flow.mmd)).

**Phase 2.6**: the Admin Center gained a fourth top-level resource —
**Groups** — plus an application-centric ("who/what has access to this
app?") view alongside the existing user-centric one, and the User Detail
screen was refactored from a single long page into tabs. See "Groups
screens", "Applications detail (app-centric)", and "User Detail (tabbed)"
below. The underlying `/api/admin/*` contract, service split, and every
Phase 2/2.5 business rule described in this document otherwise still apply
unchanged — this is an additive extension, not a rebuild
(`docs/platform/access-groups.md` "Architecture decisions").

**Phase 2.5**: the Admin Center is now served by its own app
(`apps/admin-web`, proxied at `/admin`) calling its own zero-database API
service (`apps/admin-api`, port 8001), which forwards every request to
`platform-api` and enriches DijiTalentFlow client names/counts from
`talent-api`. The screens, business rules, and public `/api/admin/*`
contract below are byte-for-byte unchanged from Phase 2 — see
`docs/platform/service-architecture.md` "Admin: a real HTTP client, not a
shared database" for what moved and why.

The Admin Center is a privileged platform module within DijiOne — not a
separate product — visible only to users whose resolved
`platform_permissions` include `platform.admin.access` (SUPER_ADMIN or
PLATFORM_ADMIN). It inherits the DijiOne design system (warm red/orange
gradient sidebar, cream active state, white cards) so it feels like a
natural part of the platform, not a bolted-on backoffice tool.

## Navigation

```text
Administration
├── Dashboard        /admin                    user/module/admin counts, pending review count
├── Users            /admin/users              every DijiOne identity
│   └── User Detail  /admin/users/[id]         tabbed: Overview / Applications / Groups /
│                                               Client Access / Effective Access / Audit History
├── Applications      /admin/applications       module registry (DijiTalentFlow/Birthday/Spark)
│   └── App Detail    /admin/applications/[key] assigned users + assigned groups, app-centric
├── Groups             /admin/groups             reusable access groups (list)
│   └── Group Detail   /admin/groups/[id]        members + per-module role/scope grants
├── Roles              /admin/roles              role catalog with permission/user counts
├── Permissions        /admin/permissions        permission catalog, grouped by module + category
├── Client Access      /admin/client-access      staff client/portfolio scope, all in one place
└── Audit              /admin/audit              every administrative change
```

`AdminShell` (`apps/admin-web/src/app/admin-shell.tsx`) gates the whole
subtree with `usePlatformAdmin()` — a non-admin persona sees an empty-state
explaining why, with a link back to DijiOne Home, never a broken page.
Every admin screen keeps a persistent "Back to DijiOne Home" footer link
(CR §36).

## Backend enforcement

The frontend gate above is a UX convenience only. Every `/api/admin/*`
request `admin-api` receives is forwarded to `platform-api`'s internal
`/api/platform/admin/*` surface with the *original caller's* bearer
token — `platform-api` re-derives the actor's permissions from that token
itself via `require_platform_admin` at minimum; mutating routes
additionally depend on `require_platform_permission(...)` for the specific
action (`platform.admin.manage_users`, `platform.admin.manage_admins`
implicitly via `AdminService`'s own check, `platform.admin.view_audit`).
`admin-api`'s own word for who is calling is never trusted on its own — see
`docs/platform/authorization.md` and `docs/platform/service-contracts.md`
"Service-to-service trust boundaries".

## User Detail (tabbed, Phase 2.6)

`apps/admin-web/src/app/users/[id]/page.tsx` was refactored from a single
long page into six tabs — same underlying data and mutations as Phase 2/2.5,
reorganized rather than rebuilt:

- **Overview** — status toggle and platform role selector (CR §26; same
  `PATCH /api/admin/users/{id}/status` / `.../platform-role` endpoints as
  before).
- **Applications** — one editor card per registered module
  (`ModuleAssignmentEditor`), unchanged from the pre-2.6 single-page layout:
  - **Enabled** checkbox — disabling immediately removes the module from
    that user's DijiOne Home ("My Apps") on their next request, enforced
    server-side by `GET /api/modules` filtering on `UserModuleRole.enabled`.
  - **Role** select — populated from `GET /api/admin/roles` filtered to that
    module, so an administrator picks "Talent Acquisition Member" rather
    than typing `TA_MEMBER` (CR §49 — no raw permission strings required).
  - **Client Scope** — "All Clients" checkbox, or a checkbox list of
    specific clients (CR §22/§30 portfolio scope), backed by
    `PUT /api/admin/users/{id}/modules/{module_key}`. The client id→name
    mapping is resolved by `admin-api` calling `talent-api`'s
    `/api/talent/internal/clients-lite` — if `talent-api` is down, the
    picker still functions with ids shown instead of names rather than
    failing outright (`docs/platform/failure-isolation.md`).
  - Modules with no roles defined yet (DijiBirthday, DijiSpark) render as a
    read-only card explaining that no functional roles exist yet — their
    assignment editor is intentionally inert rather than fake (CR §4.2/4.3).
- **Groups** (new) — the groups this user is an active member of, with
  add/remove. `AdminUserOut` does not carry a `groups` field, so the page
  derives membership client-side: it fetches every group via
  `listAdminGroups()`, then each group's detail via `getAdminGroup(id)`, and
  filters to the ones whose `members` list contains this user id. This is a
  deliberate, documented shortcut — fine at the platform's current group
  count, but a dedicated `GET /api/admin/users/{id}/groups` endpoint would
  be the right fix if the group count grows (see "Known gaps" below).
- **Client Access** — the same staff client/portfolio scope view previously
  shown inline, now its own tab.
- **Effective Access** (extended) — see "Effective Access view" below.
- **Audit History** (new) — `listAdminAudit({entity_type: "User", entity_id})`
  scoped to this user, reusing the existing `/admin/audit` data rather than
  a new endpoint.

## Effective Access view

`GET /api/admin/users/{id}/effective-access` resolves — not just
displays — the user's actual permission set per module plus their platform
permissions, using the same `AuthorizationService` the API itself uses for
every request. This guarantees the Effective Access panel can never show
something the backend wouldn't actually enforce (CR §31).

**Phase 2.6**: the resolved permission set per module is now the *additive*
union of direct assignment and every active group's assignment (see
`docs/platform/effective-access.md` for the exact resolution rule). Each
module's `EffectiveModuleAccessOut` gained a `sources: list[AccessSourceOut]`
field — one entry per contributing role, each tagged `type: "DIRECT"` or
`type: "GROUP"` (with `group_name` when group-derived). The Effective Access
tab renders this as a `DIRECT` badge or an `INHERITED FROM <Group Name>`
badge (`StatusBadge` tone map) next to each permission, so an administrator
can see *why* a user has a given access without leaving the tab.

## Groups screens (Phase 2.6)

`apps/admin-web/src/app/groups/page.tsx` (list) and
`apps/admin-web/src/app/groups/[id]/page.tsx` (detail):

- **List** — Group, Description, Members count, Applications count, Status,
  with a "Create Group" action (`Modal` form) calling
  `POST /api/admin/groups`.
- **Detail** — member list with add/remove (user search reuses
  `listAdminUsers`, backed by `POST/DELETE /api/admin/groups/{id}/members`),
  plus a module assignment editor per app — the same
  `ModuleAssignmentEditor` pattern as the User Detail Applications tab,
  generalized to target a group instead of a user
  (`PUT/DELETE /api/admin/groups/{id}/modules/{module_key}`).
- **SYSTEM group protection** — a group with `group_type === "SYSTEM"` has
  its delete/deactivate controls disabled in the UI, and the backend
  independently rejects the same operation
  (`AdminService.set_group_status` raises `SystemGroupProtectedError` on a
  `SYSTEM` group; see `docs/platform/access-groups.md` "SYSTEM group
  protection"). The frontend check is a convenience, not the enforcement.

Groups are the group-centric complement to the user-centric Applications
tab described above — see `docs/platform/access-groups.md` for the full
model and admin workflows (both user-centric and application-centric).

## Applications detail (app-centric, Phase 2.6)

`apps/admin-web/src/app/applications/[key]/page.tsx` — reached from a card
on the existing `/admin/applications` grid — gives an app-centric view of
who/what has access to one module, the mirror image of the user-centric
User Detail page:

- app info and service status (same runtime-status source
  `docs/platform/failure-isolation.md` describes elsewhere);
- **Assigned Users** table — every direct `UserModuleRole` for this module;
- **Assigned Groups** table — every `GroupModuleRole` for this module;
- **"+ Assign User" / "+ Assign Group"** actions, each opening a role +
  client-scope form identical in shape to `ModuleAssignmentEditor`.

Backed by `GET /api/admin/applications/{module_key}`
(`AdminService.application_detail`), which returns assigned direct users +
assigned groups + role/scope/status per principal in one payload — this is
new, not a client-side recombination of existing endpoints.

## SUPER_ADMIN lockout & admin-role protection (CR §50)

Enforced in `AdminService`, independent of any frontend check:

- deactivating or demoting the **last** active SUPER_ADMIN is rejected
  (403) with a clear message;
- granting/revoking SUPER_ADMIN or PLATFORM_ADMIN requires the caller to
  already hold `platform.admin.manage_admins` (SUPER_ADMIN only) — a
  PLATFORM_ADMIN attempting this receives 403.

Covered by `apps/platform-api/tests/test_platform_admin.py` (the business
rules themselves) and `apps/admin-api/tests/test_admin_api.py` (that
`admin-api` correctly forwards and translates `platform-api`'s responses,
including its own `503` when `platform-api` is unreachable).

## Audit

`/admin/audit` reads the same `AuditLog` table every business workflow
already writes to (talent request created/reviewed, etc.), filtered/sorted
by recency. Every admin mutation appends actor, action, entity, and
before/after JSON state — no separate admin-only audit store was
introduced (CR §41 — "do not create redundant parallel authorization
systems"). Phase 2.6 group mutations log through the same
`AuditService.log(...)` call with `entity_type="AccessGroup"` — see
`docs/platform/access-groups.md` "Audit" for the action list.

## Users list improvements (Phase 2.6)

`apps/admin-web/src/app/users/page.tsx` gained search (name/email) and
client-side filters (application, role, active/inactive) over the existing
`listAdminUsers()` result — no new backend query parameters were added,
consistent with the dataset's current small size (CLAUDE.md §8 scope
discipline).

**Known gap**: the Users list does not have a group-count column or a
group filter. `AdminUserOut` does not carry a `groups` field; adding one
would need a backend change, and doing that client-side (like the User
Detail Groups tab does for one user) would mean N group-detail fetches per
row on the list screen — judged not worth it at current scale. Left as a
documented gap rather than solved with an N+1 fetch pattern.

## What is intentionally not built in this phase

- Role/permission **creation or deletion** UI — the catalog is seeded and
  system-protected (`Role.is_system=True`); CR §28 allows this to come
  later "if it can be done safely within this phase," and extending an
   already-large schema change with a full role editor was judged out of
  scope for the MVP window (CLAUDE.md §8 — scope discipline).
- Per-client-per-staff-user restriction below the module-role level beyond
  what `UserModuleClientScope` already provides.
- DijiBirthday / DijiSpark functional administration — placeholders only.
