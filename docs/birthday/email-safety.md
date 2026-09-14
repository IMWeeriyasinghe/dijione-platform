# DijiBirthday — Email Safety (non-production outbound-recipient allowlist)

> Authoritative. Ownership: **DijiBirthday only** — this feature is
> deliberately not implemented in DijiOne platform admin, `platform-api`,
> any central shared configuration UI, or Customer Portal V2. See
> `docs/platform/email-architecture.md` for how this fits alongside
> Exchange RBAC (sender-side) as two independent safety layers.

## What problem this solves

DijiBirthday DEV/UAT send real outbound email through Microsoft Graph
(`MAIL_TRANSPORT=graph`) using the shared `appassistant@dijitalteam.com`
mailbox. Exchange RBAC for Applications (see `email-architecture.md`)
guarantees the service can only send **as** that one mailbox — it says
nothing about which real-world inboxes a non-production environment is
allowed to send **to**. Without a second control, a DEV/UAT bug (a bad test
order, a stray "send all" script, a copy-pasted real supplier address) could
land a real email in a real supplier's inbox from a non-production
environment. Email Safety closes that gap: in DEV/UAT, DijiBirthday will
only actually submit an email to an address an internal administrator has
explicitly approved through this feature.

## Data model

`BirthdayTestEmailRecipient` (`apps/birthday-api/app/models/birthday_test_email_recipient.py`,
migration `ab10ac1cdce1`):

| Field | Notes |
|---|---|
| `email_address` | As entered, for display |
| `normalized_email_address` | Trimmed + lowercased; unique, indexed — the sole match key |
| `display_label` | Free text, e.g. "Madushanka - Internal Test" |
| `recipient_type` | `INTERNAL_TESTER` \| `TEST_SUPPLIER` |
| `is_active` | Deactivate instead of delete for the normal offboarding path |
| `created_by` / `updated_by` / `created_at` / `updated_at` | Standard provenance |

**Deliberately no `environment` column.** DEV/UAT/PROD are already
physically separate databases (`birthday_dev`/`birthday_uat`/`birthday_prod`
— `docs/platform/service-architecture.md`), so DEV's rows are already
impossible to see from UAT or PROD; an `environment` column would be
redundant and could invite a bug where a query forgets to filter it.

**No wildcard/domain-wide support, anywhere, structurally.** Validation
(`app/services/test_email_recipient_service.py`) has no code path that
treats `*` as meaningful; a `*@dijitalteam.com`-style entry is rejected at
create/update time with a clear error. Only exact addresses are ever
approved.

## Mail-policy integration

`app/integrations/factory.py`:

```python
def _build_policy(db: Session | None) -> MailPolicy:
    ...
    if settings.mail_policy != "internal_allowlist":
        return ProductionPolicy() if settings.mail_policy == "production" else DisabledPolicy()
    if db is None:
        return DisabledPolicy()          # fail closed — no db session, no send
    try:
        allowlist = list_active_recipient_emails(db)
    except Exception:
        return DisabledPolicy()          # fail closed — DB error, no send
    return InternalAllowlistPolicy(allowlist)
```

`_get_transport()` (which mailbox/credential to use) stays `@lru_cache`'d —
that never changes at runtime, and caching preserves `GraphMailTransport`'s
Graph token cache. `_build_policy()` is deliberately **not** cached: it
re-queries `BirthdayTestEmailRecipient` fresh on every `get_email_client(db)`
call, which is what makes an admin's activate/deactivate action in the
Email Safety UI take effect on the very next send — no redeploy, no
container restart, no env var change.

Every failure mode fails **closed**: no DB session, a DB error, an
unrecognized `MAIL_POLICY` value, or a recipient simply not on the list all
produce `DisabledPolicy`/`BLOCKED` — never a silent fall-through to
"allowed." `mail_policy=production` never consults this table at all, so a
real supplier is never required to be manually approved.

## No CC/BCC — "multiple recipient safety" holds by construction

`MailClient.send()`/`GraphMailTransport.send()`/every `order_email_service.py`
call site take exactly one `to: str` parameter — there is no CC/BCC anywhere
in the current mail model. A valid, approved primary recipient can
therefore never let an unapproved CC/BCC bypass the allowlist, because
there is no second recipient channel to bypass it with. If CC/BCC is added
later, it must be threaded through the same `MailPolicy.check()` call before
`MailClient.send()` reaches the transport.

## Admin API (DijiBirthday-local, non-production-only)

`apps/birthday-api/app/api/routes/admin.py`, under `/api/birthday/admin/test-email-recipients`:

| Method | Path | Notes |
|---|---|---|
| GET | `/test-email-recipients` | List all (active + inactive) |
| POST | `/test-email-recipients` | Create — 409 on duplicate (case-insensitive), 422 on invalid/wildcard |
| PATCH | `/test-email-recipients/{id}` | Update `display_label` / `recipient_type` / `is_active` — the address itself is not editable; delete + recreate to change it |
| DELETE | `/test-email-recipients/{id}` | Hard delete — for a genuine mistake, not normal offboarding; prefer `is_active=false` |

Authorization: the existing Birthday internal RBAC permission
`birthday.config.manage` (same permission the detection/config admin
surface already uses) — no new auth mechanism was invented. Supplier
portal users, anonymous requests, and internal users without that
permission are all rejected (403/401), proven by
`apps/birthday-api/tests/test_email_safety_admin.py`.

**Every route depends on `require_non_production()` first**, before the
permission check or any DB work:

```python
def require_non_production() -> None:
    if get_settings().is_production:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
```

This 404s the entire admin surface in PROD **independently of the
frontend** — hiding the "Email Safety" nav item in `birthday-web` is a UI
convenience, never the actual security boundary. `is_production` is
`app_env == "prod"`, matching `deploy/bicep/main.bicep`'s
`APP_ENV` value exactly.

## Frontend: `birthday-web` → Admin → Email Safety

Route: `/admin/email-safety` (`apps/birthday-web/src/app/admin/email-safety/page.tsx`).

- Nav item ("DijiBirthday → Admin → Email Safety") is gated on
  `scope.isAdmin && releaseMeta?.is_production === false` — a strict
  equality to `false`, not just "not yet true," so it stays hidden during
  `/api/meta`'s loading state in every environment rather than flashing
  visible in PROD momentarily.
- `is_production` is served by the existing runtime `/api/meta` Route
  Handler (`force-dynamic`, reads `process.env.APP_ENV` at request time) —
  the same mechanism and rationale as the footer's `RELEASE_DATE`: this
  platform builds one image and promotes the identical digest
  DEV → UAT → PROD, so a `NEXT_PUBLIC_*` build-time flag would be wrong the
  moment that image ran in a different environment
  (`docs/platform/versioning.md`).
- The page itself shows a banner: *"Test Email Safety is active in this
  environment. Only approved recipients can receive real outbound
  DijiBirthday email."* — plus a note that this control never applies in
  production.
- Table (desktop) / card list (mobile/tablet, same breakpoint pattern as
  Suppliers/Orders): Email Address, Label, Type, Status, Created By/At,
  Updated By/At, Actions. Add/Edit uses the shared `Modal` + `FormField`
  components; client-side validation is a UX convenience only — the
  backend re-validates syntax, duplicates, and wildcards regardless.

## Initial DEV recipients

Seeded idempotently via `apps/birthday-api/scripts/seed_test_email_recipients.py`
(a standalone script, not an Alembic data migration — this repo's migrations
only ever change schema, never seed environment-specific business data):

1. `madushanka.weeriyasinghe@dijitalteam.com` — "Madushanka - Internal Test" — `INTERNAL_TESTER`
2. `madusankaweeriyasinghe20@gmail.com` — "Test Supplier - Gmail" — `TEST_SUPPLIER`

Both are ordinary rows after seeding — editable/deactivatable through the
UI like any other recipient, never hardcoded in `order_email_service.py` or
anywhere else in the mail-sending business logic. Re-running the script is
a no-op for addresses that already exist (matched on
`normalized_email_address`).

## Audit

Recorded through `AuditService` (`apps/birthday-api/app/services/audit_service.py`)
— Platform Core's central `AuditLog`, the same mechanism every other
Birthday admin action already uses; this feature does not introduce a
second/local audit system. Event types: `TEST_EMAIL_RECIPIENT_CREATED`,
`TEST_EMAIL_RECIPIENT_UPDATED`, `TEST_EMAIL_RECIPIENT_ACTIVATED`,
`TEST_EMAIL_RECIPIENT_DEACTIVATED`, `TEST_EMAIL_RECIPIENT_REMOVED` — each
carries actor id, recipient id/email, and previous/new state where
applicable. A blocked outbound send itself is traced through the existing
`SupplierCommunication.transport_outcome = "BLOCKED"` +
`SupplierCommunication.last_error` fields (`docs/platform/email-architecture.md`'s
delivery-status model) — no separate blocked-send audit table.

## Environment behavior summary

| Environment | `MAIL_POLICY` | Email Safety UI | Admin API | Enforcement |
|---|---|---|---|---|
| DEV | `internal_allowlist` | Visible (admin only) | Available | DB-backed allowlist, fail-closed |
| UAT | `internal_allowlist` | Visible (admin only) | Available | Same design, **own** UAT DB — rows never propagate from DEV |
| PROD | `production` | Never shown | 404 (`require_non_production`) | No test-recipient administration exists; real suppliers never need manual approval |

## UAT rollout (documented, not yet deployed)

UAT needs, independently of DEV:

- Its own `birthday-api` Container App with its own system-assigned
  Managed Identity.
- Its own Exchange service-principal registration
  (`DijiBirthday-Uat-API-MI`), its own `DijiApps-AppAssistant-Mailbox-Scope`
  role assignment (`DijiBirthday-Uat-MailSend`) — same runbook as DEV
  (`docs/platform/email-architecture.md`), against UAT's own identity.
- Its own `birthday_uat` database — the `ab10ac1cdce1` migration applies
  there the same way it did in DEV; UAT's `BirthdayTestEmailRecipient` rows
  are seeded and administered independently (the seed script is safe to
  run there too, but UAT is free to have a different approved-recipient set
  from DEV).
- `MAIL_TRANSPORT=graph`, `MAIL_POLICY=internal_allowlist`,
  `MAIL_SHARED_MAILBOX=appassistant@dijitalteam.com` on UAT's `birthday-api`
  Container App.
