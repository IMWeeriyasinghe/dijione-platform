# Employee directory, employee records and default access

| Concern | Authority | How DijiOne reads it |
|---|---|---|
| Authentication identity | Microsoft Entra | sign-in (OIDC) and, read only, Microsoft Graph with platform-api's managed identity |
| Employee record (HR) | BambooHR | people-api's internal contract (`EmployeeDirectoryClient`, `WorkforceDirectoryClient`) |
| Application authorisation | DijiOne | platform-api (roles, groups, client scopes, default access) |

## Adding employees

Admin Center → Users → **Add User** searches the Entra directory as the administrator types. The
search is server-side and returns at most 15 enabled internal member accounts. Guests, disabled
accounts and other domains are excluded. Each result shows the photo, title, department, Employee
Number and whether the person is **In BambooHR**. Selecting a person sends only the Entra object id.
platform-api re-reads the account from Graph, refuses duplicates (409 with `existing_user_id`), and
creates a profile that is already **directory verified**. Manual entry remains a fallback; such a
profile awaits directory verification (**Verify with directory** on the user page).

## Identity and employee record are separate facts

- **Identity verified** (`internal_employee` + Entra object id): from directory verification or a
  verified Microsoft sign-in.
- **Employee record** (`employee_record_status`):
  - `MATCHED`: the work email equals an active BambooHR employee's, or the directory's employeeId
    equals the Employee Number of exactly one active BambooHR entry.
  - `NOT_FOUND`: BambooHR answered and no record matched.
  - `UNKNOWN`: BambooHR could not be read. This never grants anything and never overwrites a known
    state.
  - `LEGACY`: a migration-only state for people who held default access before these checks. It is
    kept and reported for HR reconciliation, never silently revoked.
- **Eligible employee** = active, identity verified, and employee record `MATCHED` or `LEGACY`.
  Eligibility gates default employee access and View-as. An Entra member account with a company
  address (a service account, a shared mailbox) is not enough on its own. Explicit assignments
  never depend on eligibility.

`POST /api/admin/employee-records/reconcile` (manage users) re-checks every verified identity. It
turns `LEGACY` into `MATCHED` where it can and lists the remaining `LEGACY` people as HR exceptions.

## Default access (always on)

DijiAtWork `ATWORK_USER` (`module_baseline_roles`) is held by every eligible employee, including
before their first sign-in. It cannot be removed by user, group or application administration while
the person stays eligible. Higher roles (`ATWORK_MANAGER`) add to it. No other application has
default access: DijiTalentFlow, DIJI Birthday and Diji On-site remain explicitly assigned.

## Pre-login View-as

A Super Admin with `platform.admin.view_as` can view an eligible employee who has never signed in.
The token, read-only enforcement, expiry, revocation and auditing are unchanged
(`docs/platform/view-as.md`). For a profile that is not eligible, the Admin Center shows the access
preview without starting a session.

## Photos and Entra groups

Photos come from `GET /users/{id}/photos/96x96/$value`, served by platform-api with private caching.
The browser never receives a Graph token. With no photo, initials are shown. Entra group
memberships (direct and inherited) are shown read only on the user page. They are not DijiOne
access groups, they grant nothing, and they are changed only in Microsoft Entra.

Graph permissions and setup: `deploy/README.md`, "Directory read for platform-api". MFA:
`docs/platform/mfa-conditional-access.md`.
