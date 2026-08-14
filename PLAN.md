# DijiOne Platform — Build Plan

Status: Phase 1 (First Autonomous Run) complete; Phase 2 (Identity,
Authorization, Administration) complete; Phase 2.5 (Application-Level
Service Separation) complete; Phase 2.6 (Enterprise Access Management +
Intelligent Home) complete. See `docs/mvp-status.md` for the full
checklist and quality-gate results of all four phases.
Authoritative contract: [CLAUDE.md](./CLAUDE.md), extended by the DijiOne
Phase 2 change request (identity/authorization/Admin Center), the
Phase 2.5 change request (service separation — see
`docs/platform/service-architecture.md`), and the Phase 2.6 change request
(access groups + effective access + Home redesign — see
`docs/platform/access-groups.md`).

## Repository state at start

Repository was blank except `CLAUDE.md` and `.claude/settings.json`. No git
history existed. This plan documents the bootstrap from zero.

## Architecture decision (superseded by Phase 2.5 — see below)

The layout below was the Phase 1/2 architecture. Phase 2.5 replaced it with
eight application-level services; this section is kept as the historical
record of the starting point the ADR at `docs/decisions/0001-monorepo-
layout.md` and the Phase 2.5 change request both explicitly designed
around. Current architecture: `docs/platform/service-architecture.md`.

Modular monolith per CLAUDE.md §6 (Phase 1/2, no longer current):

- `apps/web` — one Next.js 15 App Router application hosting the DijiOne
  shell and all module UIs (including DijiTalentFlow).
- `apps/api` — one FastAPI application exposing platform + module APIs.
- `modules/talent-flow` — DijiTalentFlow domain documentation/fixtures owned
  by the module; actual route/service code lives inside `apps/web` and
  `apps/api` under module-scoped folders to avoid Next/FastAPI multi-package
  build complexity during the MVP, per §8 "may adapt exact folder placement
  to framework constraints".
- `packages/*` — shared TS types/config used by `apps/web` (documented, not
  a separate publishable package during MVP — see ADR 0001).
- `integrations/*` — provider adapter documentation; actual adapter code
  lives in `apps/api/app/integrations/{lever,hubspot}` since FastAPI cannot
  import across a JS workspace boundary. Directories are kept as documented
  extension points per repository structure guidance.

## Phases

- [x] Phase 0 — Planning, repo inspection, docs skeleton
- [x] Phase 1 — DijiOne platform foundation (Next.js shell, FastAPI, SQLite,
      Alembic, design tokens, module registry, dev identity)
- [x] Phase 2 — DijiTalentFlow core (Client + TA workspaces, domain model,
      demo data)
- [x] Phase 3 — Workflow & security (CS review state, notifications, audit
      log, tenant isolation tests)
- [x] Phase 4 — Mock integration architecture (LeverClient, HubSpotClient,
      ExternalMapping, IntegrationEvent, webhooks)
- [x] Phase 5 — 55-65% review point / quality gates (lint, build, pytest,
      ruff, migrations) — see `docs/mvp-status.md` for full results
- [ ] Phase 6+ — Live discovery / production hardening — NOT started; blocked
      on credentials by design, not a blocker for this run.

## Phase 2 — Identity, Authorization & Admin Center

- [x] Centralized `AuthorizationService` + Role/Permission/RolePermission
      catalog (`app/core/permissions.py`, single source of truth for the
      Alembic backfill and `scripts/seed.py`).
- [x] Client/portfolio scope (`UserModuleClientScope`) replacing the
      "one client or all clients" limitation with an explicit portfolio.
- [x] `SUPER_ADMIN` platform role + lockout/admin-role-change protection.
- [x] DijiOne Admin Center: backend (`/api/admin/*`) + frontend
      (`/admin/*`, 8 pages).
- [x] Module assignment `enabled` flag; `User` Phase 2 identity fields
      (`entra_object_id`, `identity_provider`, `last_login_at`).
- [x] Microsoft Entra ID OIDC integration seam extended
      (`/api/auth/entra/*`) — not activated, fails fast with 501 until
      real tenant credentials exist.
- [x] Admin audit logging (reuses existing `AuditLog`, no new store).
- [x] Regression: all 18 Phase 1 tests still pass unmodified; 17 new
      Phase 2 tests added (`test_authorization_phase2.py`,
      `test_admin_center.py`).
- [x] Docs: `docs/platform/authorization.md`, `docs/platform/admin-center.md`
      (new); `authentication.md`, `module-framework.md`, `architecture.md`
      updated.

## Phase 2.5 — Application-Level Service Separation

- [x] `platform-api` extracted: owns identity, authorization, module
      registry, audit log, notifications; issues JWTs with signed
      authorization claims.
- [x] `packages/auth-client-py` built: claims verification +
      `PlatformClient` HTTP wrapper shared by every business service.
- [x] `admin-api` extracted as a zero-database service — forwards to
      `platform-api` with the caller's own bearer token, enriched from
      `talent-api`.
- [x] `talent-api` extracted: owns its own database, authorizes from
      claims, audit/notification writes are best-effort HTTP calls.
- [x] `birthday-api` / `spark-api` skeletons: health/metadata/summary +
      the same claims-based auth seam, no business logic.
- [x] `packages/design-system`, `packages/auth-client-ts`,
      `packages/contracts` extracted from `apps/web`; `shell-web`,
      `admin-web`, `talent-web` split out as independent Next.js zones
      behind `shell-web`'s gateway.
- [x] Root npm workspace + `npm run dev:all` starts all eight services.
- [x] `apps/web` and `apps/api` deleted after extraction was verified.
- [x] Regression: 74 backend tests + 6 package tests, all frontend apps
      build/lint clean, live browser smoke test including a real
      `talent-api` outage/recovery cycle.
- [x] Docs: `docs/platform/service-architecture.md`,
      `service-contracts.md`, `failure-isolation.md`,
      `local-development.md` (new); `architecture.md`, `authorization.md`,
      `admin-center.md`, `module-framework.md`, `authentication.md`,
      `mvp-status.md`, this file (updated).
- [x] Diagrams: service architecture, service boundaries, gateway
      routing, data ownership, failure isolation, local dev topology,
      future Azure deployment.

## Phase 2.6 — Enterprise Access Management + Intelligent Home

- [x] `AccessGroup` / `UserGroupMembership` / `GroupModuleRole` /
      `GroupModuleClientScope` models (`apps/platform-api/app/models/access_group.py`),
      additive alongside the existing direct-assignment tables; new Alembic
      migration.
- [x] `AuthorizationService` extended with `groups_for_user`,
      `effective_module_roles`, `effective_client_scope`,
      `effective_permissions` — additive-ALLOW resolution (union of direct +
      active-group grants; ALL_CLIENTS overrides a concrete-client-list
      contributor). Single resolution engine: `AdminService.effective_access`
      and `claims_service.build_claims` both consume these same methods.
- [x] `AdminService` group CRUD + `application_detail` (app-centric admin
      view); SYSTEM-type groups protected from deactivation.
- [x] New routes: `apps/platform-api/app/api/routes/platform_admin.py`
      (`/groups/*`, `/applications/{module_key}`) and mirrored pass-through
      routes in `apps/admin-api/app/api/routes/admin.py`.
- [x] New TS contracts in `packages/contracts/src/types.ts`
      (`AccessGroupOut`, `AccessGroupDetailOut`, `AccessSourceOut`,
      `ApplicationDetailOut`, extended `EffectiveModuleAccessOut`).
- [x] `admin-web`: new Groups list/detail screens, new Applications detail
      screen, User Detail refactored into six tabs (Overview / Applications
      / Groups / Client Access / Effective Access / Audit History) with
      `sources`-based DIRECT/INHERITED-FROM badges, Users list search +
      client-side filters, new "Groups" nav item.
- [x] `shell-web`: Home reordered (Header → My Apps → Needs Your Attention
      → Recent Activity + Platform Health + Ask DijiOne), new
      `AttentionPanel.tsx` and `PlatformHealth` components (role-aware,
      real-data-only, isolated per-service fetches), `ModuleCard.tsx` shows
      operational summary fields + resolved role per app, COMING_SOON
      modules visually de-emphasized.
- [x] Regression: 40 new `platform-api` tests + 12 new `admin-api` tests,
      all passing alongside the full pre-2.6 suite; both frontend apps build
      clean.
- [x] Docs: `docs/platform/access-groups.md`, `docs/platform/effective-access.md`
      (new); `authorization.md`, `admin-center.md`, `module-framework.md`,
      `service-architecture.md`, `mvp-status.md`, this file (updated).

## 2026-08-14 (part 2) — Live BambooHR activation, eligibility rule, address verification

Real BambooHR credentials (`BAMBOOHR_API_KEY`, `BAMBOOHR_SUBDOMAIN`) were
supplied and added to `apps/birthday-api/.env` (gitignored;
`INTEGRATIONS_MODE=live`). Live discovery findings, exact tenant field
names, and validation results are in
`docs/platform/bamboohr-live-discovery.md`. Summary:

- [x] **Live connection verified** — 484 employee records via BambooHR's
      Custom Report API, read-only, no writes at any point.
- [x] **Real field names confirmed and wired**: `displayName` (not
      first+last concatenation), `birthday` (BambooHR's own MM-DD derived
      field — no year), `status` (`Active`/`Inactive`, the sole
      authoritative active-flag — `employmentHistoryStatus` was surveyed
      and rejected as a fallback, since it holds employment *type*, not
      active/inactive), `hireDate` (always populated), `terminationDate`
      (real date or the sentinel `"0000-00-00"`, normalized to `None` in
      `app/integrations/bamboohr/mapper.py`). `app/integrations/bamboohr/
      http_client.py` rewritten to match; `app/integrations/bamboohr/
      schemas.py`'s `BambooHREmployee` gained `display_name`, `hire_date`,
      `termination_date`.
- [x] **Confirmed live**: an employee can show `status=Active` in
      BambooHR *before* their hire date (9 of 326 active records observed
      2026-08-14) — validates that hire-date must be checked independently
      of status, not inferred from it.
- [x] **Central eligibility rule** — new
      `app/services/eligibility_service.py`: active + hire date <=
      birthday occurrence + no termination before occurrence + valid
      birthday exists, returning `(eligible: bool, EligibilityReason)`.
      Backend-only, single source of truth — wired into both
      `directory_service.list_upcoming_birthdays` (informational —
      ineligible employees still appear, flagged, never silently dropped)
      and `detection_service.run_daily_scan` (a hard gate — an ineligible
      employee never gets a `BirthdayOrder` row created at all).
- [x] **Address verification workflow** — new
      `AddressVerificationStatus` enum (`NOT_CHECKED`,
      `VERIFICATION_REQUESTED`, `VERIFIED`, `NEEDS_UPDATE`,
      `NOT_APPLICABLE`), new `BirthdayOrder.address_verification_status`
      column (Alembic migration `cb458018416c`, default `NOT_CHECKED`),
      new `app/services/address_verification_service.py` (P&C-manual only,
      no automated employee contact, every change audited via the existing
      `AuditService` + a new `ADDRESS_VERIFICATION_CHANGE` `OrderEvent`
      entry — no address content ever logged, only status values + an
      optional note), new `PATCH
      /api/birthday/orders/{id}/address-verification` route.
- [x] **Cake-order gate extended** — `order_email_service._send()` now
      raises `AddressNotVerifiedError` (409, order stays visible as
      "needs P&C action", never silently dropped) unless
      `address_verification_status == VERIFIED`, on top of the
      pre-existing supplier-assignment/status-transition checks. Existing
      `(employee_id, birthday_year)` unique constraint and `quantity=1`
      default preserved exactly as before — untouched.
- [x] **Supplier-facing DTO** — new `SupplierOrderView` schema +
      `order_service.to_supplier_view()`: fulfilment facts + a boolean
      `address_verified` flag only, no HR eligibility logic, hire dates,
      internal status enum, or eligibility reasons. Actual supplier-portal
      auth/routes remain Phase F (`SupplierUser` model already documented
      "portal built in Phase F" before this change) — deliberately not
      built now, per CLAUDE.md §8 scope discipline; automated supplier
      email/order sending remains gated off exactly as before.
- [x] **Frontend** — `apps/birthday-web/src/app/upcoming/page.tsx` now
      shows Hire Date, Eligibility (grouped: Upcoming & Eligible / Needs
      Attention / Future Starter / Not Eligible, with a filter dropdown)
      and Address Verification columns; `OrderDetail.tsx` gained an
      Address Verification card with a P&C status selector and an
      explicit "never contacts the employee automatically" note; Send to
      Supplier is now also disabled until `address_verification_status ==
      VERIFIED`. `packages/contracts/src/types.ts` extended
      (`BirthdayOrderSummary`/`Out` gained `address_verification_status`;
      `UpcomingBirthdayItem` gained `hire_date`, `eligible`,
      `eligibility_reason`, `address_verification_status`; new
      `AddressVerificationUpdateInput`).
- [x] **Tests**: 28 new backend tests (`test_eligibility_service.py`,
      `test_address_verification.py`, `test_bamboohr_integration.py`,
      additions to `test_directory_service.py`/`test_detection.py`/
      `test_order_email_service.py`) covering eligibility (active+hired,
      hire==today, future hire, inactive, terminated-before-birthday,
      missing birthday/hire date), the 7-day/Dec→Jan/duplicate-retry/
      future-starter-never-orders detection scenarios, address
      verification (default, P&C change, audit entry, send-gate
      before/after), and BambooHR integration (real-tenant-shaped mapping,
      API unavailable, missing field, unexpected status value, malformed
      date). Full regression: `birthday-api` 97 passed, `platform-api` 44,
      `admin-api` 12, `talent-api` 27 — 180 backend tests total, all
      passing; `birthday-web` production build + eslint clean.
- [x] Live validation (read-only, no writes): 484 employees returned, 326
      active, 24 eligible upcoming birthdays in the next 30 days, 0
      missing-hire-date records, 6 missing-birthday records (correctly
      excluded), no API/permission limitations hit. Full detail in
      `docs/platform/bamboohr-live-discovery.md`.
- **Workflow readiness**: Live Birthday Retrieval — READY. Eligibility
      Filtering — READY. 7-Day/window Detection — READY (existing scan
      logic, now eligibility-gated). Address Verification — READY
      (manual P&C workflow, UI + audit trail complete). Order Creation —
      READY (eligibility + idempotency both enforced). Approval — NOT
      BUILT (no distinct approval step exists beyond
      hold/release/cancel — out of scope for this change). Supplier
      Visibility — PARTIAL (DTO exists, portal auth/routes are Phase F,
      not built). Supplier Email — GATED OFF (automation intentionally
      not enabled; manual send-to-supplier now additionally gated on
      address verification). Failure/IT Handling — READY (existing
      `REQUIRES_ATTENTION` exception queue + audit logging, now also
      covers BambooHR fetch failures and malformed-record skips without
      PII).

## 2026-08-14 — Navigation performance investigation + BambooHR live-directory endpoint

- [x] **Performance investigation.** Measured cold-vs-warm route timing in
      dev (`npm run dev:all`, curl-based) vs. a production build
      (`next build && next start`) for `shell-web` and `birthday-web`.
      Root cause confirmed: dev-mode Turbopack per-route compilation
      (cold dynamic route ~1.0-1.4s vs. warm ~0.02s via curl alone),
      amplified by the multi-zone architecture's requirement that
      cross-zone navigation be a full browser page load (plain `<a>`, not
      `next/link` — each zone process pays its own first-visit compile
      tax). Production build showed **no** cold/warm gap (all routes
      15-80ms) — confirms this is dev-only, not a production defect. No
      duplicate API calls, missing `prefetch`, sequential blocking
      fetches, N+1 queries, or per-request config reloads were found — all
      already handled correctly. No application code changes were made
      (nothing to fix); `docs/platform/local-development.md`'s existing
      dev-mode-compile note was extended to cover `birthday-web` and
      reference the full measurement writeup. See
      `docs/platform/performance-investigation.md`.
- [x] **BambooHR live-directory endpoint for DijiBirthday.** Found the
      DijiBirthday module (`birthday-api`/`birthday-web`) already far more
      built than expected — a full cake-order workflow already existed
      (suppliers, order sequencing, detection scan, dashboard,
      `BirthdayOrder` with a DB-level `UniqueConstraint(employee_id,
      birthday_year)`, `MockBambooHRClient` with active-only filtering on
      `employment_status`). What was genuinely missing: a **live**
      `BambooHRClient` implementation (the factory raised "not implemented
      in this phase") and a directory-style "upcoming birthdays" view
      independent of whether the daily detection scan has already run.
      Added:
      - `app/integrations/bamboohr/http_client.py` — `BambooHRHttpClient`,
        config-gated (`BAMBOOHR_API_KEY`, `BAMBOOHR_SUBDOMAIN`), calling
        BambooHR's Custom Report API for `dateOfBirth`/`status`, raising
        `BambooHRNotConfiguredError` until both are set; wired into
        `app/integrations/factory.py`. Not exercised against a real tenant
        — no BambooHR credentials were available (CLAUDE.md §58) — but no
        redesign will be needed to drop real credentials in later.
      - `app/services/directory_service.py` /
        `app/schemas/birthday_directory.py` /
        `app/api/routes/employees.py` — `GET
        /api/birthday/employees/upcoming-birthdays?days=30`, returning
        `employee_id`, `display_name`, `birthday` (MM-DD),
        `days_until_birthday`, `department`, `location`,
        `cake_order_status` (`"not_created"` stub when no `BirthdayOrder`
        row exists yet for that employee/year — the existing unique
        constraint remains the one idempotency seam, not duplicated
        here). Year-boundary birthdays verified correct via
        `compute_next_birthday_occurrence` (already existed, reused as-is).
        BambooHR fetch failures and per-record malformed-data skips are
        audit-logged with no PII, matching the existing
        `IntegrationEvent`/audit-log convention.
      - `apps/birthday-web/src/app/upcoming/page.tsx` rewired from the
        older order-based `/api/birthday/upcoming` view to this new
        BambooHR-backed endpoint; empty state now reads "No active
        employee birthdays found within the next N days.", loading/error
        states preserved, existing warm orange/red design tokens
        untouched.
      - `apps/birthday-api/tests/test_directory_service.py` (12 new
        tests): active-employee inclusion, inactive/terminated exclusion,
        days-until calculation, year-boundary calculation, out-of-window
        exclusion, empty roster, BambooHR fetch failure (audited, no PII),
        malformed birth-month/day skipped without failing the request,
        `cake_order_status` reflecting a real existing order, endpoint
        response shape, and auth enforcement.
      - Regression: full `birthday-api` suite 65/65 passing (53 pre-existing
        + 12 new), `ruff check` clean; `platform-api` 44/44,
        `admin-api` 12/12, `talent-api` 27/27 all still passing;
        `birthday-web` production build and `eslint` both clean.
      - Note: two background agents were briefly launched in parallel for
        this work before being redirected to run inline — their partial,
        in-progress edits (the BambooHR agent's `http_client.py`,
        `employees.py`, `directory_service.py`, `.env.example` additions)
        were inspected, reconciled, completed, and verified by hand
        rather than discarded, since they were consistent with the
        existing repo conventions.
      - What remains before the 7-day cake-ordering workflow (approval +
        supplier email) can be activated: nothing schema/seam-related —
        `BirthdayOrder`'s unique constraint, `order_status_service`,
        `order_email_service`, and supplier resolution already exist from
        an earlier phase. What's still open is exclusively the live
        BambooHR credential (Phase D per CLAUDE.md §59) and, if desired,
        deciding whether the daily detection scan's cron/scheduler trigger
        (currently an internal-token-protected manual endpoint,
        `test_scan_run_endpoint_*` in `test_detection.py`) should be
        automated — out of scope for this change.

See `docs/mvp-status.md` for the full Definition-of-MVP-Done checklist and
`docs/decisions/0001-monorepo-layout.md` for the repository-layout ADR
referenced below.

## 2026-08-14 (part 3) — BambooHR employee identity fix (Phase-Next §1 of 8)

Full plan: `C:\Users\Dell\.claude\plans\you-are-working-on-sprightly-ritchie.md`
(DijiBirthday Phase-Next: Identity Fix, Approval Workflow, Order CRUD,
Table Overhaul, Supplier Portal).

**Bug found and fixed**: the app stored/displayed BambooHR's internal
record `id` as "Employee ID". Verified live against the `dijitalteam`
tenant (read-only Custom Report query) that for Madushanka Weeriyasinghe,
`id="366"` but the real operational Employee ID (BambooHR's
`employeeNumber` field) is `"239"`. Fixed by adding a new, separate
`employee_number` column/field throughout the stack — `employee_id`
(BambooHR internal id) is preserved unchanged as the idempotency/join key,
`employee_number` is the new user-facing identifier.

**Shipped this pass**:
- `BambooHREmployee.employee_number`, `_REPORT_FIELDS` now requests
  `employeeNumber`, both live and mock BambooHR clients populate it.
- New `BambooHRClient.get_employee(employee_id)` single-lookup method
  (live + mock), used only by the backfill script.
- `BirthdayOrder.employee_number` column (nullable, indexed) — Alembic
  migration `a1b2c3d4e5f6` (additive, mirrors the existing
  `address_verification_status` migration's pattern), applied.
- `scripts/backfill_employee_numbers.py` — idempotent, re-runnable,
  reports `{updated, skipped_already_current, skipped_no_bamboohr_number,
  failed_lookup}`. Run against the local dev DB (0 rows — no
  `BirthdayOrder` rows exist locally yet, so nothing to backfill; script
  is correct and ready for when real order data exists).
- `employee_number` threaded through `detection_service`,
  `directory_service`, `order_service.create_or_get_order`, the manual
  order-create route, all relevant Pydantic schemas, and
  `packages/contracts/src/types.ts`.
- Frontend: `orders/page.tsx`, `OrderDetail.tsx`, `upcoming/page.tsx` now
  display `employee_number` (falling back to a visibly-labeled
  `employee_id` when a given employee has no `employeeNumber` in
  BambooHR).
- Backend: 97/97 tests pass (fixed two test doubles that needed the new
  abstract `get_employee` method; updated one exact-shape assertion for
  the new field). `ruff check` clean.

## 2026-08-14 (part 4) — Approval workflow, order CRUD, search/filter/sort, supplier portal + app (Phases 2–8)

Continuation of the same plan (`C:\Users\Dell\.claude\plans\you-are-working-on-sprightly-ritchie.md`),
completing all remaining sections in one autonomous pass per explicit
instruction. All phases below are **COMPLETE**.

**Phase 2 — Approval workflow**: `OrderStatus` gains `DRAFT` /
`READY_FOR_APPROVAL` / `APPROVED` (`REJECTED` already existed); new
`app/services/readiness_service.py` (single readiness check: address
verified, supplier assigned, office/quantity/name present); new
`order_status_service.submit_for_approval/approve/reject`; new endpoints
`POST /orders/{id}/{submit-for-approval,approve,reject}`,
`GET /orders/{id}/readiness`. Auto-detected orders now default `DRAFT`
(was `PLANNED`); manual orders too. `order_email_service._send` gates on
`status in (APPROVED, REQUIRES_ATTENTION)` — new `ApprovalRequiredError`.
New permissions `birthday.orders.approve`/`.delete`.

**Phase 3 — Order CRUD gaps**: `BirthdayOrder` gains `delivery_date`,
`catalogue_item_id` (FK to `SupplierCatalogueItem`); `PATCH /orders/{id}`
accepts `supplier_id` (reassignment, writes `SUPPLIER_ASSIGNED` event),
`delivery_date`, `catalogue_item_id`; new `DELETE /orders/{id}` — 409
unless `status == DRAFT` and no `SupplierCommunication` rows exist.

**Phase 4 — Search/filter/sort/pagination**: `BirthdayOrderRepository`/
`SupplierRepository`/`directory_service.list_upcoming_birthdays` all gained
`search`/`sort_by`/`sort_direction`; `GET /orders`, `GET /suppliers`,
`GET /employees/upcoming-birthdays` all return a stable `{items, total,
page, page_size}` envelope (breaking response-shape change, updated
`lib/api.ts` accordingly). New shared
`packages/design-system/src/ui/DataTable.tsx` (`SearchInput`, `SortableTh`,
`Pagination`, `useSortToggle`) — closes the CLAUDE.md §54 gap. Orders,
Suppliers, and Upcoming Birthdays pages rebuilt on it; group filtering for
Upcoming Birthdays moved server-side (`directory_service.group_for`).

**Phase 5 — Supplier API security boundary**: new `SupplierScope`/
`get_supplier_scope`/`require_supplier_permission` (`app/api/deps.py`),
resolving `supplier_id` exclusively from a new `supplier` JWT claim
(`packages/auth-client-py`'s `AuthClaims.supplier: SupplierClaims | None`
— additive, verified non-breaking for talent-api/platform-api). New
`app/api/routes/portal.py`: `GET /portal/orders`, `GET /portal/orders/{id}`,
`POST /portal/orders/{id}/acknowledge`, `PATCH /portal/orders/{id}/status`
(allow-listed transitions only), `POST /portal/orders/{id}/issue`.
`BirthdayOrderRepository.get_for_supplier`/`list_for_supplier` scope every
query by `supplier_id` and additionally only ever return
already-sent (`SENT_TO_SUPPLIER`+) orders — a `DRAFT` order is never
supplier-visible. Extended `SupplierOrderView` (id, employee_name,
delivery_date, catalogue_item_name, status) — still a genuinely separate
schema, HR fields never selected into it. 9 dedicated cross-supplier
isolation tests (`tests/test_supplier_portal.py`), the single most
important new test set per CLAUDE.md §14.

**Phase 6 — `apps/birthday-supplier-web`**: new, independently
buildable/deployable Next.js app (port 3006, own `package.json`/
`next.config.ts`/`tsconfig.json`/`eslint.config.mjs`), added to the root
`workspaces` array. Only ever calls `/api/birthday/portal/*` — no shared
API client with `birthday-web`. Pages: `/` (orders list), `/orders/[id]`
(detail + acknowledge/status-progress/raise-issue actions), a login
screen that will redirect into Entra B2B guest OIDC in production and
renders a dev persona picker locally. No password/magic-link form
anywhere in this app.

**Auth**: production target is Microsoft Entra ID B2B guest
(`SupplierUser.entra_object_id`, new nullable+unique column, migration
`b2c3d4e5f6a7`). Local/dry-run: new `app/api/routes/dev_auth.py`
(`GET/POST /api/birthday/internal/dev/supplier-*`) — hard-404s when
`APP_ENV=production` (verified by test), mints a token whose `supplier`
claim is resolved server-side from the chosen `SupplierUser` row, never
from a client-supplied `supplier_id`. 3 dedicated tests
(`tests/test_dev_supplier_auth.py`).

**Phase 7 — Dry run, email disabled**: new independent `EMAIL_SENDING_MODE`
config (`app/core/config.py`, default `mock`), `get_email_client()` now
switches on it instead of the shared `INTEGRATIONS_MODE` — BambooHR stays
`live` in `.env` while `EMAIL_SENDING_MODE=mock` is now explicit there
too. 10 end-to-end tests (`tests/test_dry_run_e2e.py`): full automatic
BambooHR→detection→approval→send→supplier-portal→delivery workflow, the
ad hoc internal-create workflow, and every named exception scenario
(future starter, inactive/terminated, duplicate/idempotent, missing
supplier, missing fulfilment info, rejected, cancelled, supplier unable
to fulfil) — all assert `MockGraphEmailClient` only, never a real Graph
call.

**Phase 8 — Docs**: `docs/birthday/requirements.md` rewritten to describe
the approval-gated workflow as current (superseding the exception-based
V1 description) and lists everything shipped this phase plus what remains
deferred (Entra B2B guest tenant-side provisioning, inbound reply-capture
automation, Cowork API access, dedicated approval-queue UI page).

**Verification**: `apps/birthday-api` — 127/127 tests pass (was 97 at the
end of part 3), `ruff check` clean, two new Alembic migrations applied
clean (`a1b2c3d4e5f6`, `b2c3d4e5f6a7`). `apps/platform-api` (44/44) and
`apps/talent-api` (27/27) re-verified with no regressions from the shared
`auth_client_py`/`permissions.py` changes. `birthday-web` and the new
`birthday-supplier-web`: both `npm run build` and `npm run lint` clean.
Real supplier email sending confirmed disabled throughout
(`EMAIL_SENDING_MODE=mock` verified by dedicated test + `.env` inspection).

## Notes

- No production credentials available or requested. Mock providers only.
- SQLite for local dev, PostgreSQL-compatible schema via SQLAlchemy 2.
- Dev Identity Mode replaces Entra ID locally; seam documented in
  `docs/platform/authentication.md`. Phase 2 kept this seam intact —
  Dev Identity Mode and the target Entra ID flow both resolve through the
  same `AuthorizationService`, only identity acquisition differs.
