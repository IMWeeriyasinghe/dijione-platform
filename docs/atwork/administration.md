# DijiAtWork — administration responsibilities

DijiAtWork has two separate levels of administration.

| | Level 1: DijiOne central administration | Level 2: DijiAtWork Management |
|---|---|---|
| Where | Existing DijiOne Admin Center | `/atwork/management` |
| Owner | Platform Core (`platform-api`, `admin-api`, `admin-web`) | `atwork-api`, `atwork-web`, the future `atwork_<env>` database |
| Manages | Users, SSO identity, application access, DijiAtWork role assignment (direct or through Access Groups) | Application settings, management workflows, DijiAtWork business records and policies |
| Must not | Hold DijiAtWork business rules or records | Store users, assign roles or provide a separate login |

## Default employee access

Platform Core derives `ATWORK_USER` for every eligible internal employee from
`module_baseline_roles`, with no per-user rows. Home, tokens, the Admin Center and
API checks read the same result. Eligible means active, signed in through Entra, in
our tenant, not a guest, and on an `ENTRA_INTERNAL_EMAIL_DOMAINS` domain. The marker
is refreshed at each sign-in, so existing users qualify at their next one.

`ATWORK_MANAGER` is never default: assign it directly or through an Access Group. To
revoke one employee's default access, save a disabled `ATWORK_USER` assignment. Access
changes reach existing sessions when the token renews, at most 12 hours later.

## How access works

1. Microsoft Entra authenticates the user; `platform-api` issues the DijiOne token.
2. An administrator assigns `ATWORK_USER` or `ATWORK_MANAGER` in the Admin Center.
3. `AuthorizationService` resolves direct and group grants into signed token claims.
4. `atwork-api` verifies the claims locally and enforces a permission on each protected route.
5. `atwork-web` uses `/api/atwork/me` for navigation only.

A change to a role takes effect when the user's token is next issued.

| Role | `atwork.access` | `atwork.management.access` |
|---|---|---|
| `ATWORK_USER` | Yes | No |
| `ATWORK_MANAGER` | Yes | Yes |

Business permissions are added to the catalog only when their features are
approved. Code checks permissions, never role names.
