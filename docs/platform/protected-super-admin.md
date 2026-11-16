# Protected Super Admin

A protected administrator keeps the platform role `SUPER_ADMIN` and an active account whatever any
other administrator, including another Super Admin, does in DijiOne. It is not a new role and not a
permission: it is a policy row that the existing admin services and a database-flush guard enforce.

## Identity

`protected_admins` holds the policy: the normalised e-mail address (stable across environments, no
database ids) and the Entra object id, recorded the first time the person is linked to a Microsoft
sign-in. Rows are written only by an Alembic migration. Migration `j6l8n0p2q4r5` registers
`madushanka.weeriyasinghe@dijitalteam.com`, sets that existing account to `SUPER_ADMIN` (nothing else
about the account changes), raises that user's `access_version` and writes one audit entry. If the
account does not exist yet, the policy is registered and the role is applied at the first verified
internal Entra sign-in (`protected_admin.converge`). No user is ever created by the migration.

## What is refused (server side, in the same transaction)

For the protected account, through any DijiOne API, service or ORM path:

- changing the platform role away from `SUPER_ADMIN` (including to `PLATFORM_ADMIN`/`PLATFORM_USER`);
- deactivating or deleting the account;
- changing the e-mail address, or re-binding the Entra identity (the first binding is allowed);

and for the policy itself: editing or deleting a policy row, renaming or deleting the `SUPER_ADMIN`
role, or detaching a permission from it. The Admin services refuse first, with a clear 403 and an audit
entry `protected_admin.change_blocked`; `app/services/protected_admin.py` (a SQLAlchemy `before_flush`
guard) is the backstop for any path that was not pre-checked. No endpoint creates, edits or toggles
protection. Application access (modules, groups, client scope) of the protected user stays
manageable, and other Super Admins stay manageable through the normal workflow.

Every verified sign-in re-applies the required state (`SUPER_ADMIN`, active) for a protected account
and records its Entra object id.

## Admin Center

The user page shows a lock icon with **Protected Super Admin**, the explanation “This account's
Super Admin privilege is protected and cannot be removed by other administrators.”, a disabled
platform-role selector, and a disabled Deactivate button.

## Infrastructure-level recovery (not an application path)

If the account is ever damaged by something outside DijiOne (for example a restored backup), an
operator with access to the environment's PostgreSQL server restores it with direct SQL, which does
not pass through the application:

1. confirm the identity: `SELECT id, email, platform_role, is_active, entra_object_id FROM users WHERE lower(email) = '<protected email>';`
2. `UPDATE users SET platform_role = 'SUPER_ADMIN', is_active = true WHERE id = <id from step 1>;`
3. `python -m app.services.access_version` (raises every session version, so new sessions carry the role).

Removing the protection itself requires deleting the `protected_admins` row with direct SQL by an
operator, outside the application. This is a deliberate, audited-by-Azure operation, not an
application permission and not a Super Admin override.
