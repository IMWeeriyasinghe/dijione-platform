# Access notifications — standard for DijiOne applications

When a person's access to a platform-managed application changes, DijiOne emails them. This
applies whether the change is made in Admin Center or on the application's own Access page. An
application gets this **by following the access-management contract below**, with no email code
of its own. Mechanism and event list: `email-notifications.md`. Architecture: `email-architecture.md`.

## Platform-managed staff access (the default for every module)

### Contract
1. **Register the module, roles and permissions** in the platform catalog through a platform-api
   migration (`module-framework.md` "Adding a new module"). The registry `name` is the application
   name used in email subjects, for example `[Diji On-site] | Access Granted`. It must not contain
   `[`, `]` or `|`. If it does, the email falls back to `[DijiOne]` rather than being lost.
2. **Give the module a `route`** in the registry: a path on the DijiOne host such as `/onsite`.
   Single-application emails link to it.
3. **Delegated administration**, if wanted: add a `DelegationDef` (`app/core/permissions.py`) and
   mount the shared `AccessManagementPage` from `@dijione/design-system`.
4. **Write access only through `AdminService` or `DelegatedAccessService`.** Never use Core bulk
   `insert`/`update`/`delete` on access tables (`user_module_roles`, group roles and memberships,
   client scopes, administrators, suspensions, `users.platform_role` / `is_active`). Bulk
   statements skip the ORM flush the notification listener relies on.
5. **Add the contract test** (below) to the module's platform-api test coverage.

### What the platform does for you
- **Detection:** the change is detected inside the access transaction. A rolled-back change never
  emails, and a committed change is never lost.
- **Classification and subject:**
  - Granted, Revoked, Role Updated, Client Access Updated, Access Administration Updated and
    Access Updated each have their own event.
  - Exactly one application changed: the subject uses the module's registry name.
  - First access, deactivation or several applications: one `[DijiOne]` email.
- **Suppression:**
  - No-op changes.
  - Changes of source only (direct versus group).
  - Changes inside default access.
  - Global toggles and catalog edits; those are silently realigned.
  - View-as sessions, which cannot mutate anything.
- **Delivery:** retries, folding of quick follow-up changes, delivery history, admin retry with
  stale-email protection, event switches, and DEV/UAT test-recipient allowlists.
- **Origin** for administrators: the channel, source application, actor and audit ids, taken only
  from the transaction's own audit rows.

### Contract test (copy into the module's tests)
`apps/platform-api/tests/test_access_notifications_v2.py::test_application_access_page_sends_application_specific_emails`
runs for **every** key in `DELEGATION`. A module that adds a `DelegationDef` is covered
automatically. If the module has no delegation, assert the Central Admin path the same way:
```python
def test_<module>_access_emails(db, world, api_client):
    central(api_client, person.id, "<module>", "<ROLE>")          # Central Admin grant
    row = rows(db, person.id)[-1]
    assert row.application_key == "<module>"
    assert row.subject == f"[{name_of(db, '<module>')}] | Access Granted"
```
Keep module names out of shared code and tests: iterate `DELEGATION` or the registry instead.
`scripts/check-module-independence.js` enforces this.

### Release checklist
- [ ] Registry row has `name` and `route`, added by a migration.
- [ ] Roles and permissions are in the catalog; `DelegationDef` is added if delegation is wanted.
- [ ] Access writes go only through `AdminService` / `DelegatedAccessService`.
- [ ] Contract test passes. The module-independence and module-removal CI jobs are green.
- [ ] DEV: a real access change for an allowlisted test account, checked in Admin > Notifications
      (SUBMITTED) and in the recipient's inbox.
- [ ] UAT: the same. PROD needs release authorization.

## Application-owned external populations (not platform users)

Some applications manage their own external users in their own database. Examples are the
DIJI Birthday supplier portal (`supplier_users`) and TalentFlow client magic links
(`magic_link_grants`). platform-api never sees these, so they are **not** covered above.
An application that wants to email them:
- **Uses the shared library** `packages/mail-client-py` (`format_subject`, `render_email`,
  `GraphMailTransport`), with its **own** durable outbox written in the same transaction as the
  change, its **own** managed identity and Exchange assignment (`deploy/runbooks/exchange-mail-rbac`),
  and its **own** DEV/UAT allowlist (`email-architecture.md` adoption checklist).
- **Never posts events to platform-api.** Internal service authentication is a shared secret with
  no per-caller identity, so a cross-service "send this email" endpoint could be forged.

| Population | Owner | Today | Next phase (needs approval) |
|---|---|---|---|
| Birthday supplier users | birthday-api | Invitation email | Deactivation and role-change emails through birthday-api's existing Graph client |
| TalentFlow client magic links | talent-api | Copy-only links, no email | Owner decision; would need talent-api's own outbox, identity and Exchange assignment |
