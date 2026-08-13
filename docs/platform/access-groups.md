# DijiOne Access Groups (Phase 2.6)

Access Groups are a reusable, additive layer of authorization on top of the
existing direct-assignment model introduced in Phase 2 — a way to say
"everyone on the TA Team gets DijiTalentFlow access" instead of assigning
that access to each user individually. They are strictly additive: the
Phase 2 `UserModuleRole`/`UserModuleClientScope` tables, and every code path
that reads them directly, are untouched. See `docs/platform/authorization.md`
"Access Groups (Phase 2.6)" for how groups feed into the authorization
engine, and `docs/platform/effective-access.md` for the precise resolution
algorithm.

## Why groups, not just direct assignment

Direct assignment (Phase 2) requires every user/app/client combination to be
assigned individually — correct, but doesn't scale to team-based
administration. Access Groups let an administrator grant a module role
(with client scope) once, to a group, and have it apply to every current and
future member of that group without a per-user edit. Groups compose with
direct assignment rather than replacing it: a user can simultaneously hold a
direct `UserModuleRole` and inherit further access from one or more groups;
their effective access is the union (see "Composition with direct
assignment" below).

## Model

Four new tables, all owned by `platform-api`
(`apps/platform-api/app/models/access_group.py`):

```text
AccessGroup
  id, key (unique), display_name, description,
  status (ACTIVE | INACTIVE), group_type (free-form, e.g. TEAM/CLIENT/SYSTEM)

UserGroupMembership
  id, user_id -> users.id (CASCADE), access_group_id -> access_groups.id (CASCADE)
  unique (user_id, access_group_id)

GroupModuleRole
  id, access_group_id -> access_groups.id (CASCADE), module_key, role, enabled
  (mirrors UserModuleRole's shape)

GroupModuleClientScope
  id, group_module_role_id -> group_module_roles.id (CASCADE),
  client_id (nullable int, no FK), all_clients (bool)
  (mirrors UserModuleClientScope's shape)
```

`GroupModuleClientScope.client_id` is a plain opaque integer, exactly like
`UserModuleClientScope.client_id` — no foreign key into `talent-api`'s
`clients` table. This preserves the no-cross-service-FK rule (see
`docs/platform/service-architecture.md` "Data ownership across services").

### `group_type` semantics

`group_type` is a free-form classification string set at group creation —
`TEAM`, `CLIENT`, and `SYSTEM` are the values in use, but the column is not
an enum at the database level.

- **`TEAM`** / **`CLIENT`** — ordinary administrator-managed groups. No
  special protection; can be created, edited, deactivated, and (via status)
  effectively retired like any other group.
- **`SYSTEM`** — reserved for groups the platform itself depends on.
  `AdminService.set_group_status` rejects any attempt to deactivate a
  `SYSTEM` group with `SystemGroupProtectedError` (surfaced as a 403),
  independent of any frontend check — the "Deactivate" control is also
  disabled in the Admin Center's Groups UI, but that's a convenience, not
  the enforcement (`apps/platform-api/app/services/admin_service.py`).

### Group membership

`UserGroupMembership` is a plain many-to-many join between `User` and
`AccessGroup` — a user can belong to any number of groups, and a group can
have any number of members. Only membership in an `ACTIVE` group
contributes to effective access (`AuthorizationService.groups_for_user`
filters on `AccessGroup.status == ACTIVE`); membership rows in an inactive
group are not deleted, they simply stop contributing.

### Group module assignments

`GroupModuleRole` grants a module-scoped role to every active member of the
group, the same way `UserModuleRole` grants one to a single user directly.
`enabled=False` on a `GroupModuleRole` disables that grant for every member
without deleting the row (mirrors `UserModuleRole.enabled`). Client/
portfolio scope for a group module assignment is expressed the same way as
direct assignment: `GroupModuleClientScope` rows under a `GroupModuleRole`,
with `all_clients=True` meaning unrestricted, or a set of concrete
`client_id` rows meaning a restricted portfolio. No scope rows at all is
treated as unrestricted, the same pre-Phase-2 back-compat default
`AuthorizationService.client_scope_for` already uses for direct assignment.

## Composition with direct assignment

Access Groups never replace direct assignment — they're a second, additive
source that `AuthorizationService` unions with it. There is no DENY
semantics in this phase: a group can only add access, never take it away
from what a direct assignment already grants (and vice versa). The exact
role/permission/client-scope union rules are documented precisely in
`docs/platform/effective-access.md`, since getting that rule right is the
one piece of Phase 2.6 that most needs to be unambiguous.

## Admin workflows

The Admin Center supports both administration angles on the same
underlying data — see `docs/platform/admin-center.md` for the screens:

- **User-centric** — from a user's detail page (`/admin/users/[id]`), the
  **Groups** tab shows which active groups that user belongs to, with
  add/remove; the **Applications** tab still edits their direct assignment
  per module; the **Effective Access** tab shows the resolved union with
  per-permission `DIRECT`/`INHERITED FROM <Group>` provenance.
- **Group-centric** — `/admin/groups` (list) and `/admin/groups/[id]`
  (detail) manage a group's membership and its per-module role/scope
  grants directly, independent of any one user.
- **Application-centric** — `/admin/applications/[key]` shows, for one
  module, every directly-assigned user and every assigned group side by
  side, with "+ Assign User" / "+ Assign Group" actions — the view an
  administrator reaches for when the question is "who/what can access
  DijiTalentFlow?" rather than "what can this one user access?".

All three views read and write the same underlying tables through the same
`AdminService` methods — there's exactly one set of group CRUD/assignment
operations (`create_group`, `update_group`, `set_group_status`,
`add_group_member`, `remove_group_member`,
`upsert_group_module_assignment`, `remove_group_module_assignment`), just
surfaced from three different entry points in the UI.

## Backend routes

`apps/platform-api/app/api/routes/platform_admin.py`, gated by
`require_platform_admin`/`require_platform_permission` the same as every
other admin route (`platform.admin.manage_users` is reused for group
mutations rather than introducing a new permission key):

```text
GET    /groups
POST   /groups
GET    /groups/{id}
PATCH  /groups/{id}
PATCH  /groups/{id}/status
POST   /groups/{id}/members
DELETE /groups/{id}/members/{user_id}
PUT    /groups/{id}/modules/{module_key}
DELETE /groups/{id}/modules/{module_key}
GET    /applications/{module_key}
```

`apps/admin-api/app/api/routes/admin.py` mirrors these under
`/api/admin/groups/*` and `/api/admin/applications/{module_key}` as pure
pass-through routes, forwarding the caller's own bearer token to
`platform-api` — the same zero-database pattern every existing `admin-api`
route uses (see `docs/platform/service-architecture.md` "Admin: a real HTTP
client, not a shared database").

## Audit

Every group mutation goes through the existing `AuditService.log(...)` call
into the same `AuditLog` table every other admin mutation and business
workflow already writes to — no new audit store was introduced. New action
values, all with `entity_type="AccessGroup"` (member add/remove additionally
use `entity_type="UserGroupMembership"`):

```text
access_group.created
access_group.updated
access_group.member_added
access_group.member_removed
group_module_assignment.upserted
group_module_assignment.removed
```

Visible in the Admin Center's existing `/admin/audit` screen and, per-user,
in the User Detail page's new Audit History tab.
