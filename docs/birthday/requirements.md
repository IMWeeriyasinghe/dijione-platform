# DijiBirthday — Requirements & Scope

DijiBirthday automates employee birthday-cake ordering, sourced live from
BambooHR. **As of Phase-Next (2026-08-14), this is an explicit
approval-gated workflow**, not the exception-based pass-through V1 shipped
with: every order — auto-detected or manually created — starts `DRAFT`,
auto-promotes to `READY_FOR_APPROVAL` once eligible/address-verified/
supplier-assigned, and requires an explicit human `APPROVE` action before
it may become supplier-visible. The exception queue (`REQUIRES_ATTENTION`)
remains for genuine fulfilment failures (send errors, resend recovery),
but is no longer the mechanism that gates normal orders from
supplier-visibility — approval is.

Full requirement detail, data model, API surface, and phase breakdown live in
the implementation plan this module was built from:
`C:\Users\Dell\.claude\plans\dijibirthday-end-to-end-piped-axolotl.md` (kept
outside the repo as the planning artifact; this file is the in-repo pointer
`docs/platform/module-framework.md` references).

## V1 (shipped — Phases A–D)

- Domain model: `BirthdayOrder`, `Supplier`, `SupplierLocation`,
  `SupplierCatalogueItem`, `SupplierUser`, `SupplierCommunication`,
  `OrderEvent`, `SpecialRequirement`, `BirthdayDetectionConfig`,
  `OrderSequence` (`apps/birthday-api/app/models/`).
- Idempotent BambooHR-driven detection: `POST /api/birthday/internal/run-daily-scan`,
  enforced via a DB-level unique constraint on `(employee_id, birthday_year)` —
  never a duplicate order regardless of retries.
- Window-based detection (not exact-N-day), with lead-time classification
  (Normal / Short-Notice / Urgent) compared against the resolved supplier's
  actual `lead_time_days` to decide auto-proceed vs. hold.
- Internal dashboard, Upcoming Birthdays, Cake Orders register, order detail
  with full event/status timeline, hold/release/cancel admin actions
  (`apps/birthday-web`).
- Supplier management (CRUD, locations, lightweight catalogue — no pricing in
  V1) and outbound order email via Microsoft Graph (create-draft → send
  pattern), with `order_reference` as the durable business correlation key in
  every email.
- Full audit trail via platform-api's `AuditLog`/`Notification` services on
  every state-changing action.

## Phase-Next (shipped 2026-08-14) — identity fix, approval workflow, supplier portal

- **BambooHR employee identity fix**: `BirthdayOrder.employee_id` remains
  BambooHR's internal record `id` (idempotency/join key, unchanged); a new
  `employee_number` field carries BambooHR's `employeeNumber` — the real
  operational Employee ID — and is what every UI/search/supplier-view now
  displays as "Employee ID". Verified live against the `dijitalteam`
  tenant (Madushanka Weeriyasinghe: `id="366"`, `employeeNumber="239"`).
  Backfilled for historical rows via `scripts/backfill_employee_numbers.py`.
- **Explicit approval workflow**: `OrderStatus` gains
  `DRAFT`/`READY_FOR_APPROVAL`/`APPROVED`/`REJECTED` (superseding the
  exception-based auto-`PLANNED` V1 default); `app/services/readiness_service.py`
  is the single readiness check reused by auto-promotion and the manual
  `submit-for-approval`/`approve` endpoints; `order_email_service._send`
  now requires `APPROVED` (or `REQUIRES_ATTENTION`, for resend recovery)
  before an order may reach a supplier.
- **Order CRUD completed**: `PATCH /orders/{id}` now also accepts
  `supplier_id` (reassignment), `delivery_date`, `catalogue_item_id`;
  `DELETE /orders/{id}` hard-deletes only never-actioned `DRAFT` orders
  (409 otherwise — `cancel` is the non-destructive path for everything
  else).
- **Search/filter/sort/pagination**: Orders, Suppliers, and Upcoming
  Birthdays all now support server-side `search`/`sort_by`/
  `sort_direction`/`page`/`page_size` with a stable `{items, total, page,
  page_size}` response envelope; a shared `DataTable` primitive set
  (`packages/design-system/src/ui/DataTable.tsx`) replaced three
  hand-rolled, inconsistent filter/pagination implementations.
- **Supplier API security boundary + `apps/birthday-supplier-web`**: new
  `SupplierScope` (`app/api/deps.py`) resolves `supplier_id` exclusively
  from the token's `supplier` claim — never a request parameter — and
  every `app/api/routes/portal.py` repository call is filtered on it, so
  a manipulated order id belonging to a different supplier 404s. A
  genuinely separate `SupplierOrderView` schema excludes all HR fields by
  construction. Production auth target is Microsoft Entra ID B2B guest;
  local/dry-run testing uses a hard-disabled-in-production dev persona
  provider (`app/api/routes/dev_auth.py`, `apps/birthday-supplier-web`'s
  login screen) that resolves through the same `SupplierUser -> supplier_id`
  mapping production will use.
- **`EMAIL_SENDING_MODE`**: new config flag, independent of
  `INTEGRATIONS_MODE` — lets BambooHR run live while real supplier email
  stays mocked. Defaults `mock`; flip to `live` only after this phase's
  dry run is signed off **and** Graph app registration is complete. Live
  email should notify the supplier that an approved order is available in
  the portal, not carry the full order detail — the portal is now the
  source of truth for order detail.

## Deferred (post-Phase-Next)

- Automated supplier-confirmation webhook / inbound reply capture beyond
  the portal's direct status actions (Graph reply-capture automation).
- Expanded monitoring/exception tooling beyond the `REQUIRES_ATTENTION`
  queue (approval-queue UI is the `/orders?status=READY_FOR_APPROVAL`
  filter, not yet a dedicated page).
- Cowork-ready scoped service-account API access.
- Real Microsoft Entra ID B2B guest provisioning for supplier users
  (domain model — `SupplierUser.entra_object_id` — is in place; the
  tenant-side guest invitation flow itself is not built).
