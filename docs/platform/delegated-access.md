# Delegated application access administration

DijiOne keeps identity and governance central and gives application access administration to the
people who run each application.

- **Central Admin (platform):**
  - Microsoft Entra sign-in and DijiOne users;
  - groups;
  - the application registry;
  - appointing application administrators;
  - overrides, suspensions and audit.
- **Each application's Management → Access page:** an appointed administrator grants, changes and
  removes employees' access to that application only, within the authority a Super Admin gave them.

There is one source of truth. Assignments stay in Platform Core, in the same tables Central Admin
edits, so session tokens, revocation, audit and every application's enforcement behave identically
whichever page made the change. App backends are unchanged: they keep authorizing from the session
token's permissions.

Status: merged (`ea881cd`), live in DEV, UAT and Production. The feature switch is the platform-api setting `DELEGATED_ACCESS_ENABLED`, off by default. It is declared in infrastructure code as `delegatedAccessEnabled` in `deploy/bicep/main.*.bicepparam`:

| Environment | Value |
|---|---|
| DEV | `true` |
| UAT | `true` (owner-authorized 2026-11-19, On-site v0.9.1) |
| PROD | `true` (owner-authorized 2026-11-19, On-site v0.9.1) |

The switch is shared by every registered application. With it on:
- On-site Admins can manage On-site User only. This is the implied authority from the On-site delegation definition.
- DijiTalentFlow, DIJI Birthday and DijiAtWork get no delegation until a Platform or Super Admin explicitly appoints an access administrator.

Applications that do not read client scope are flagged `supports_client_scope = false` in the registry, so their Access page asks for no client: Diji On-site, DijiAtWork, and DIJI Birthday (corrected by migration `r9t1v3x5z7b9`).

## Who does what

| Operation | Central Admin | Application administrator |
|---|---|---|
| Users, activation, platform roles, directory verification | ✓ | ✗ |
| Enable or disable an application (`platform.admin.manage_modules`) | ✓ | ✗ |
| Appoint and remove application administrators (Super Admin) | ✓ | Only with "can appoint" (off by default), own app, never beyond own authority |
| Groups and group grants | ✓ | See them; may suspend non-SYSTEM grants in their app |
| Grant, change, remove direct roles and client scope | ✓ (override) | ✓ own app, within authority |
| Add an employee straight from the directory | ✓ | ✓ if matched to BambooHR |
| Lift a suspension | ✓ | ✓ within authority |
| Audit | ✓ all | — |

## Appointment

A Super Admin appoints an eligible employee in Central Admin → Applications → *app* → Application
Administrators. An eligible employee is active, identity verified, and BambooHR MATCHED or LEGACY.

The appointment (`application_administrators`) holds the administrator's explicit authority:

| Field | Meaning |
|---|---|
| `grantable_roles` | Employee roles the administrator may grant, a subset of the app's delegable roles (`DELEGATION` in `app/core/permissions.py`). External-user roles (TALENT_CLIENT, BIRTHDAY_SUPPLIER) are never delegable. |
| `client_authority` | Client-scoped apps only. NULL means all clients; otherwise a list of client public ids. |
| `can_appoint_admins` | Off by default. Only a Super Admin can set it. |

The appointment is a grant source of its own (`APPOINTMENT`). It gives the administrator-only role
`<APP>_ACCESS_ADMIN`, or `<APP>_ACCESS_OWNER` with "can appoint".

- Those roles carry only `<app>.access.manage` (+ `<app>.access.manage_admins`), never a business
  permission.
- No assignment or group grant may use them.
- The appointment applies only while the person is an eligible employee, so a leaver loses it
  automatically.
- An administrator with no business role gets an application entry in the token and the
  application card on Home. Their shell shows only Access, and every business API refuses them; a
  test in each of the four app backends sweeps every GET route to prove it.

## Effective-access precedence

`AuthorizationService` applies the rules below. It is the single implementation behind the session
claims, `/api/auth/me`, Home, effective access, diagnostics, live permissions and role holders.

| # | Rule | Effect |
|---|---|---|
| 1 | The application is disabled in the registry | Nothing applies |
| 2 | Mandatory grants: default employee access (e.g. DijiAtWork's ATWORK_USER) and grants from `SYSTEM` groups | Always apply while their own conditions hold |
| 3 | An application suspension for this person and application | Removes direct, ordinary-group and appointment grants for this application only |
| 4 | Otherwise | Union of every grant (additive) |

## Removing access

Removing someone from the Access page:
1. A preview shows what will be removed, what will be suspended and what stays.
2. On confirm, the direct assignment is deleted.
3. If ordinary group grants would still give access, an application suspension is recorded
   (`application_access_suspensions`). It is an application-scoped deny. Group memberships, other
   applications and mandatory access are untouched.
4. Granting again lifts the suspension.

Restrictions:
- An administrator cannot suspend or change access outside their authority. That covers roles
  outside `grantable_roles` and, in Talent, clients outside `client_authority`.
- They cannot change themselves, platform administrators, protected accounts or other administrators
  of the same application.

Central Admin lists suspensions per application and can lift them.

## Onboarding from the directory

The Access page's search returns existing eligible DijiOne users, plus directory employees who are
enabled internal members AND matched to BambooHR.

Adding a directory employee (`DirectoryService.onboard_for_application`):
1. Re-reads the person from Microsoft Graph.
2. Refuses if BambooHR is NOT_FOUND or UNKNOWN, before anything is created.
3. Creates the DijiOne user and the grant in one transaction.

Application administrators never verify identities, edit profiles, see photos or Entra groups, or
change platform roles.

## Sessions, revocation, audit

Every change to an appointment, a suspension, a group's type or a person's employee-record status
raises the affected users' `access_version` through the existing listener. The applications then
refuse the old token, and the browser refreshes to the new claims. Disabling an application raises
everyone's version.

Audit entries carry `channel: CENTRAL` or `APPLICATION`, plus the application. Break-glass changes
carry `break_glass: true` and the reason, and other Super Admins are notified.

## Central hardening that ships with this

- Nobody changes their own access, including through a group they belong to. A Super Admin may do
  so only as break-glass, with a reason of at least 10 characters.
- Changing an administrator's access, activating or deactivating an administrator, and changing a
  group that has administrators as members all need `platform.admin.manage_admins` (Super Admin).
- The internal role-holders endpoint, used for notifications, resolves effective access: groups,
  suspensions, disabled apps and inactive users.
- `actor_type=staff` is mandatory on staff sessions.

## API

**Application page** (gateway `/api/access/*` → platform-api; staff sessions only, View-as is refused):

| Method | Path |
|---|---|
| GET | `/api/access/{app}/me` |
| GET | `/users` |
| GET | `/users/{id}` |
| GET | `/people?q=` |
| PUT | `/users/{id}` (grant / change) |
| POST | `/users/from-directory` |
| GET | `/users/{id}/revoke-preview` |
| POST | `/users/{id}/revoke` |
| DELETE | `/users/{id}/suspension` |
| GET, PUT, DELETE | `/admins[/{id}]` |

**Central** (admin-api → platform-api):

| Method | Path | Requires |
|---|---|---|
| GET | `/api/admin/applications/{app}/administrators` | |
| PUT, DELETE | `/api/admin/applications/{app}/administrators/{id}` | Super Admin |
| GET | `/api/admin/applications/{app}/suspensions` | |
| DELETE | `/api/admin/applications/{app}/suspensions/{id}` | `manage_users` |
| PATCH | `/api/admin/modules/{app}` `{enabled}` | `manage_modules` |

## Release

1. **platform-api with migration `q8s0u2w4y6a8`** (additive: two tables and the catalogue; no
   session is revoked), with `DELEGATED_ACCESS_ENABLED` still off. Enforcement code for suspensions
   and disabled applications is live from this step.
2. **admin-api and admin-web**, then **shell-web** (gateway route), then the four app frontends.
3. **Switch on** `DELEGATED_ACCESS_ENABLED=true` on platform-api. A Super Admin appoints the first
   administrators.

## Rollback

**Turning the feature off is always safe.** Set `DELEGATED_ACCESS_ENABLED=false` and keep the
current platform-api image:
- every `/api/access` endpoint answers 404 and no new appointment can be made;
- existing suspensions keep being enforced;
- no access is restored and nothing is changed.

Frontends can be rolled back freely, because they never decide access.

**Rolling platform-api back to an image older than this feature** (or downgrading the migration) is
allowed only when no appointment or suspension exists. An older image ignores suspensions, which
would silently give the suspended people their group access back.

1. Run `python -m app.services.delegated_access_rollback` against the environment, for example as a
   one-off `migrate-platform-api` job execution on the current image. It lists every appointment and
   suspension, and exits 1 while any exist.
2. If any exist, resolve them deliberately in Central Admin; never by bulk group changes:
   - remove appointments;
   - for each suspension, decide centrally whether the person should keep the group grant. If not,
     remove them from the group (an audited, deliberate decision about that person) and then lift
     the suspension.
3. The migration's downgrade enforces the same rule: it refuses while either table has rows.

Tests:
- `test_delegated_access_migration.py` (guarded downgrade);
- `test_delegated_access.py::test_feature_switched_off_hides_every_endpoint_but_enforcement_stays`;
- `test_rollback_check_reports_appointments_and_suspensions`.

## Not in this release (decision D6)

Per-user site scope (Diji On-site) and team scope (DijiAtWork) do not exist yet. On-site sites are
one global enabled list. Adding them is application feature work in those backends.
