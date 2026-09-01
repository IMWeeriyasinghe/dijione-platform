# DijiOne Authorization Model (Phase 2, extended Phase 2.5 / 2.6)

This document describes DijiOne's centralized authorization engine,
introduced to separate **authentication** (Microsoft Entra ID / Dev
Identity Mode — "who are you?") from **authorization** (DijiOne — "what can
you access?"), per the Phase 2 change request.

**Phase 2.5 update**: the engine below (`AuthorizationService`, the
Role/Permission catalog, `AdminService`'s SUPER_ADMIN safety rules) still
lives entirely in `platform-api` — nothing about *how* authorization is
computed changed. What changed is *how business services consume it*: pre-
split, every module's route handlers queried the same shared database
directly; post-split, `talent-api` (and, once they have real endpoints to
gate, `birthday-api`/`spark-api`) have no database access to
`platform-api`'s tables at all, and instead read the already-resolved
result from signed JWT claims. See "Claims-based authorization for
business services" below — everything above that section describes
`platform-api`'s own engine and is unchanged from Phase 2.

**Phase 2.6 update**: authorization gained a second, additive input —
**Access Groups**. A user's effective access is no longer only their own
direct `UserModuleRole`/`UserModuleClientScope` rows; it is the union of
those rows with every `GroupModuleRole`/`GroupModuleClientScope` row
belonging to a group the user actively belongs to. `AuthorizationService`
remains the single place this union is computed — see "Access Groups
(Phase 2.6)" below for the full model and "Effective access resolution
(additive ALLOW)" for the precise rule. Both `AdminService.effective_access`
(the Admin Center's Effective Access panel) and `claims_service.build_claims`
(JWT issuance) call the same new combined methods, so there is still never a
second authorization implementation anywhere in the platform.

```text
Microsoft Entra ID  =  Who are you?
DijiOne              =  What applications can you access?
Module Role          =  What responsibility do you have?
Permissions          =  What actions may you perform?
Client Scope         =  Which organization's data may you access?
```

## Entity model

```mermaid
erDiagram
    USER ||--o{ USER_MODULE_ROLE : "user_id"
    USER_MODULE_ROLE ||--o{ USER_MODULE_CLIENT_SCOPE : "user_module_role_id"
    ROLE ||--o{ ROLE_PERMISSION : "role_id"
    PERMISSION ||--o{ ROLE_PERMISSION : "permission_id"
    CLIENT ||--o{ USER_MODULE_CLIENT_SCOPE : "client_id (nullable)"

    USER {
        int id PK
        string email
        string platform_role "matches Role.key where module_key IS NULL"
        string entra_object_id "nullable, unique"
        string identity_provider
        datetime last_login_at
        bool is_active
    }
    USER_MODULE_ROLE {
        int id PK
        int user_id FK
        string module_key
        string role "matches Role.key for that module_key"
        int client_id "legacy single-tenant fast path, TALENT_CLIENT only"
        bool enabled
    }
    USER_MODULE_CLIENT_SCOPE {
        int id PK
        int user_module_role_id FK
        int client_id "nullable"
        bool all_clients
    }
    ROLE {
        int id PK
        string module_key "null = platform role"
        string key
        string name
        bool is_system
    }
    PERMISSION {
        int id PK
        string key "e.g. talent.requests.review"
        string module_key
        string category
    }
    ROLE_PERMISSION {
        int role_id FK
        int permission_id FK
    }

    ACCESS_GROUP ||--o{ USER_GROUP_MEMBERSHIP : "access_group_id"
    USER ||--o{ USER_GROUP_MEMBERSHIP : "user_id"
    ACCESS_GROUP ||--o{ GROUP_MODULE_ROLE : "access_group_id"
    GROUP_MODULE_ROLE ||--o{ GROUP_MODULE_CLIENT_SCOPE : "group_module_role_id"
    CLIENT ||--o{ GROUP_MODULE_CLIENT_SCOPE : "client_id (nullable)"

    ACCESS_GROUP {
        int id PK
        string key UK
        string display_name
        string description
        string status "ACTIVE/INACTIVE"
        string group_type "TEAM/CLIENT/SYSTEM, free-form"
    }
    USER_GROUP_MEMBERSHIP {
        int id PK
        int user_id FK
        int access_group_id FK
    }
    GROUP_MODULE_ROLE {
        int id PK
        int access_group_id FK
        string module_key
        string role "matches Role.key for that module_key"
        bool enabled
    }
    GROUP_MODULE_CLIENT_SCOPE {
        int id PK
        int group_module_role_id FK
        int client_id "nullable"
        bool all_clients
    }
```

`UserModuleRole` is DijiOne's `UserModuleAssignment` concept — the original
MVP table extended in place (not replaced) with an `enabled` flag and a
`client_scopes` relationship, per the CR's "extend, don't rebuild" mandate.
`Role` is a resolvable permission bundle layered *underneath* the existing
string-keyed `User.platform_role` / `UserModuleRole.role` columns — no
existing consumer of those columns needed to change.

## Single source of truth for the catalog

`apps/platform-api/app/core/permissions.py` defines every Role/Permission/
RolePermission row the platform ships with. Both the Alembic migration
(`f6a7b8c9d0e1_seed_authorization_catalog.py`, idempotent get-or-create —
added in Architecture Completion Plan Wave G to close a real gap: no
migration seeded this catalog before, so a freshly-migrated database had an
unusable Admin Center until someone ran `scripts/seed.py` by hand) and
`scripts/seed.py` (repeatable local reseed) import it, so a migrated
database and a fresh `--reset` reseed always end up identical.

Platform roles and their permissions:

| Role | Key permissions |
|---|---|
| SUPER_ADMIN | All `platform.admin.*` permissions, including `manage_admins` |
| PLATFORM_ADMIN | `platform.admin.access`, `manage_users`, `manage_modules`, `manage_client_scopes`, `view_audit` — **not** `manage_admins` |
| PLATFORM_USER | None (standard authenticated user; access comes entirely from module assignments) |

DijiTalentFlow roles and their permissions (see `app/core/permissions.py`
for the full 22-permission catalog): `TALENT_CLIENT` gets `_read_own` /
`_create` style permissions scoped to their own organization;
`TA_MEMBER` gets the full staff bundle (`talent.workspace.staff` plus
read/manage permissions across clients, candidates, applications,
interviews, messages, documents); `CUSTOMER_SUCCESS` and `TA_MANAGER` get
everything `TA_MEMBER` has, plus `talent.requests.review`.

## Client / portfolio scope

`TalentScope.client_ids` (resolved by `AuthorizationService.client_scope_for`)
is `None` for unrestricted (ALL_CLIENTS) access, or a list of specific
client ids for a restricted portfolio. Every tenant-scoped repository
method accepts an additive `allowed_client_ids` parameter — restricted
staff and `TALENT_CLIENT` behave identically to the pre-Phase-2
implementation when unrestricted, so no existing behavior changed for
personas that were never given a portfolio.

A module assignment with **no** scope rows at all defaults to unrestricted
— this keeps hand-created or not-yet-migrated rows working without a
mandatory backfill for every one, while the Alembic migration explicitly
backfills a scope row (or an `all_clients` row) for every pre-existing
`UserModuleRole`.

Demonstrated in seed data: the `ta-portfolio` persona (Ruwan Gunasekara) is
a `TA_MEMBER` restricted to ABC Company + XYZ Company only — Nova Solutions
is invisible to them across every DijiTalentFlow list/detail/dashboard
endpoint, verified in `tests/test_authorization_phase2.py`.

## Access Groups (Phase 2.6)

`AccessGroup` (`apps/platform-api/app/models/access_group.py`) is a
reusable, additive layer on top of direct module assignment — "everyone on
the TA Team gets DijiTalentFlow access" instead of assigning that access to
each user individually. It is strictly additive: the existing
`UserModuleRole`/`UserModuleClientScope` tables and every code path that
reads them directly are untouched. Full model and admin-workflow detail
lives in `docs/platform/access-groups.md`; this section covers only how
groups feed into the authorization engine.

- `AccessGroup.status` — `ACTIVE` or `INACTIVE`. An `INACTIVE` group, and
  every membership/module-role it has, contributes nothing to any user's
  effective access.
- `AccessGroup.group_type` — free-form (`TEAM`, `CLIENT`, `SYSTEM`, ...).
  `SYSTEM` groups are protected from deactivation by `AdminService`
  (`SystemGroupProtectedError`) — see `access-groups.md`.
- `UserGroupMembership` — a user's membership in a group. A user may belong
  to any number of groups.
- `GroupModuleRole` — a module-scoped role granted to every active member of
  the group. Same shape as `UserModuleRole` (`module_key`, `role`,
  `enabled`).
- `GroupModuleClientScope` — client/portfolio scope for a `GroupModuleRole`,
  same shape and same opaque-`client_id`-no-FK convention as
  `UserModuleClientScope`.

## Effective access resolution (additive ALLOW)

`AuthorizationService` computes a user's **effective** access to a module as
the union of their direct assignment and every active group's assignment.
There are no DENY semantics in this phase — a group or direct assignment can
only add access, never subtract it from another source.

- **Effective role(s)** for a user+module
  (`AuthorizationService.effective_module_roles`) = every distinct role from
  the user's own `UserModuleRole` (where `enabled=True`), unioned with every
  distinct role from `GroupModuleRole` (where `enabled=True`) for each group
  the user is an active member of (`AccessGroup.status == ACTIVE`).
- **Effective permissions** (`effective_permissions`) = the union of
  `_permissions_for(module_key, role)` across every distinct role
  contributing to that module, direct or group-derived.
- **Effective client scope** (`effective_client_scope`) — if **any**
  contributing assignment (direct or group) is unrestricted (`all_clients`,
  or has no scope rows at all — the same pre-Phase-2 back-compat default
  `client_scope_for` already uses), the effective scope is **ALL_CLIENTS**
  (`None`), regardless of what any other contributing assignment says.
  Otherwise, the effective scope is the **union** of concrete client ids
  across every contributing assignment's scope rows.
- **Inactive groups, disabled `GroupModuleRole` rows, and disabled direct
  `UserModuleRole` rows contribute nothing.**

Worked examples, including the ALL_CLIENTS-override-else-union interaction
and the inactive/disabled-contributes-nothing cases, are in
`docs/platform/effective-access.md`.

### Explainability: the `sources` field

Every effective grant carries its provenance. `AuthorizationService`'s
internal `ResolvedGrant` dataclass tags each contributing role
`source_type: "DIRECT" | "GROUP"` (plus `source_name` — the group's
`display_name` when group-derived). The Admin Center's Effective Access API
(`GET /api/admin/users/{id}/effective-access`) surfaces this as
`sources: list[AccessSourceOut]` per module — the admin UI renders it as a
`DIRECT` badge or an `INHERITED FROM <Group Name>` badge, so an
administrator (or this document) never has to reason about the resolution
rule by hand to answer "why does this user have this access?" — see
`docs/platform/effective-access.md` "Explainability" and
`docs/platform/admin-center.md` "Effective Access tab".

## The authorization engine (`apps/platform-api/app/services/authorization_service.py`)

```python
class AuthorizationService:
    def platform_permissions(self, user: User) -> frozenset[str]: ...
    def module_role_permissions(self, module_role: UserModuleRole) -> frozenset[str]: ...
    def client_scope_for(self, module_role: UserModuleRole) -> list[int] | None: ...

    # Phase 2.6 — additive group-aware resolution
    def groups_for_user(self, user_id: int) -> list[AccessGroup]: ...
    def effective_module_roles(self, user: User) -> dict[str, list[ResolvedGrant]]: ...
    def effective_client_scope(self, user: User, module_key: str) -> tuple[list[int] | None, list[ResolvedGrant]]: ...
    def effective_permissions(self, user: User, module_key: str) -> frozenset[str]: ...
```

The pre-2.6 single-assignment methods (`module_role_permissions`,
`client_scope_for`) are kept as-is and still used wherever only a specific
direct assignment (not the full effective picture) is relevant; they are
building blocks the new `effective_*` methods call internally, not a
parallel/duplicate authorization implementation.

Reusable FastAPI dependencies built on it
(`apps/platform-api/app/api/deps.py`) — used by `platform-api` itself and,
via pass-through, by every `/api/admin/*` request `admin-api` forwards:

```python
require_platform_admin                      # any admin (SUPER_ADMIN or PLATFORM_ADMIN)
require_platform_permission("platform.admin.manage_admins")
```

`talent-api`'s equivalent dependencies (`apps/talent-api/app/api/deps.py`)
have the identical names and shapes but resolve from JWT claims instead —
see "Claims-based authorization for business services" below:

```python
require_staff_scope                          # DijiTalentFlow cross-client staff
require_customer_success_scope               # talent.requests.review
require_talent_permission("talent.applications.create")
```

Route handlers never hardcode `if role == "TA_MEMBER"` — they depend on one
of the above. Client-supplied `role`, `client_id`, or permission values are
never trusted (CLAUDE.md §7, §33).

## Claims-based authorization for business services (Phase 2.5)

`talent-api`, `birthday-api`, `spark-api` own no `User`/`UserModuleRole`/
`AccessGroup` table — that data is `platform-api`'s. Rather than call
`platform-api` synchronously on every request (real coupling: `platform-api`
down would mean every business-service request fails, CR §21), `platform-api`
computes the caller's full authorization context **once, at login**, and
embeds it as signed claims in the JWT
(`apps/platform-api/app/services/claims_service.py`). Since Phase 2.6,
`build_claims`'s `module_roles` computation calls
`AuthorizationService.effective_module_roles`/`effective_client_scope`/
`effective_permissions` instead of iterating only the user's own
`UserModuleRole` rows, so group-derived access is included in the token —
the claim shape itself (`role`, `client_id`, `client_ids`, `permissions`) is
unchanged, so `talent-api` needed zero changes to consume it:

```json
{
  "sub": "42",
  "is_active": true,
  "full_name": "Ruwan Gunasekara",
  "platform_role": "PLATFORM_USER",
  "platform_permissions": [],
  "module_roles": {
    "talent-flow": {
      "role": "TA_MEMBER",
      "client_id": null,
      "client_ids": [1, 2],
      "permissions": ["talent.requests.read", "talent.requests.update", "..."]
    }
  }
}
```

`packages/auth-client-py`'s `decode_claims()` verifies the signature (same
HS256 secret in dev; Entra-derived claims later) and shapes the payload
into `AuthClaims`/`ModuleRoleClaims`. `talent-api`'s `get_talent_scope`
(`apps/talent-api/app/api/deps.py`) builds the exact same `TalentScope`
object the pre-split monolith did, just from `claims.module("talent-flow")`
instead of a database join — every talent-api route handler is byte-for-
byte unchanged.

**The trade-off, made explicitly**: a permission change in the Admin
Center (revoking a module role, changing client scope) takes effect the
next time the affected user's token is reissued (next login, or a future
refresh flow), not instantly. `jwt_expires_minutes` is the staleness
window. This is the documented, deliberate choice CR §21 asks for — see
`docs/platform/failure-isolation.md` "Auth: signed claims, not a live
dependency" for the full reasoning and what emergency account disabling
still does immediately versus what it doesn't.

## Frontend consumption

`GET /api/auth/me` and `POST /api/auth/dev-login` return a resolved
`platform_permissions: string[]` array alongside `module_roles`. The
frontend's `usePlatformAdmin()` / `usePlatformPermission()` hooks
(`packages/auth-client-ts/src/auth-context.tsx`, shared by all three
frontend apps) check membership in that array — never the raw
`platform_role` string — so a frontend nav decision and a backend
authorization decision can never silently drift apart. Frontend hiding
remains a UX convenience only; every route above is independently enforced
server-side.

## SUPER_ADMIN safety (CR §50)

`AdminService` enforces, independent of the frontend:

- the last active SUPER_ADMIN cannot be deactivated;
- the last active SUPER_ADMIN cannot be demoted to a non-SUPER_ADMIN role;
- only a caller holding `platform.admin.manage_admins` (i.e. a SUPER_ADMIN)
  may grant, change, or revoke SUPER_ADMIN / PLATFORM_ADMIN on any user.

## Audit (CR §35)

Every `AdminService` mutation calls `AuditService.log(...)`, capturing
actor, action, entity, timestamp, and before/after state in the existing
`AuditLog` table (no new schema needed — it already supported this shape).
Actions logged: `user.activated`, `user.deactivated`,
`user.platform_role_changed`, `module_assignment.created/updated/removed`,
and, since Phase 2.6, `access_group.created`, `access_group.updated`,
`access_group.member_added`, `access_group.member_removed`,
`group_module_assignment.upserted`, `group_module_assignment.removed`
(entity type `AccessGroup`) — see `docs/platform/access-groups.md` "Audit".
This still runs entirely inside `platform-api` (`admin-api` has no direct
database access to write to). `talent-api`'s own audit events
(`talent_request.created`, `application.stage_changed`, etc.) reach the
same `AuditLog` table via an HTTP call instead of a local write — see
`docs/platform/service-contracts.md` "Platform Core" internal endpoints
and `docs/platform/failure-isolation.md` for what happens to a talent
action when that call fails.
