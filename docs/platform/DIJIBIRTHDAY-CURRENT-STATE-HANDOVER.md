# DijiBirthday — Complete Current-State Handover Report

| Field | Value |
|---|---|
| Report generated | 2026-09-09 |
| Repository branch | `local/azure-dev-prep` |
| Repository HEAD | `96e3cc710d232a8bc8cf945a0c64cfbbcde7701e` (`96e3cc7`, `docs(birthday): supplier-portal Entra B2B architecture + DEV report update`) |
| Working tree | clean (no uncommitted changes) |
| Azure DEV inspected | Yes — read-only `az` CLI against subscription **"Dijital Team IT Production"**, resource group `rg-dijione-dev`. No Azure resource created, modified, or deleted. |
| Implementation verified against code | Yes — routes, models, migrations, services, and both frontends were read directly. Where a prior working summary disagreed with the code or the live service, the **live/code state is reported** and the discrepancy is flagged. |
| Tests executed | `birthday-api` **195 passed** (`pytest`, 136 s); `birthday-supplier-web` **6 passed** (`vitest`); `birthday-web` **2 passed** (`vitest`). |
| GitHub remote operations | **None.** No push, no PR, no branch/remote manipulation. |
| UAT / PROD touched | **None.** No UAT or PROD resource, database, or configuration was read or changed. |
| Secrets | No secret value is printed in this report. Key Vault secret **names** only. |

---

## PART 1 — Executive Summary

**Status: FUNCTIONALLY COMPLETE BUT NEEDS BUSINESS VALIDATION.**

DijiBirthday is the DijiOne platform's birthday-cake workflow-automation module. It is built, deployed to hosted Azure DEV, and passing its full automated test suite (203 tests across three apps). All of the intended DEV scope exists in code and is reachable in the hosted environment:

- a **birthday-detection engine** that reads staff from People/Workforce (`people-api`, BambooHR-backed) and idempotently creates one `BirthdayOrder` per employee per birthday-year;
- a **13-state order lifecycle** enforced by a transition table, with every transition writing an `OrderEvent` and an audit entry;
- an **internal Birthday application** (`birthday-web`, 6 pages) for the Dijital Team ops user: dashboard, upcoming birthdays + manual detection, cake-order register + per-order workflow, supplier management (locations, catalogue, supplier users);
- a **Supplier Portal** (`birthday-supplier-web`) where an external cake supplier accepts orders, drives fulfilment status, and raises problems — now fronted by **real Microsoft Entra ID B2B guest sign-in** in hosted DEV, gated by a second application-level authorization check against an ACTIVE `SupplierUser` row;
- **mock email** and **mock-free People integration** (People is live via `people-api`; Birthday email is deliberately still mocked).

**What is NOT yet done:**

1. **No real end-to-end business run has been performed in hosted DEV.** No real cake order has been detected from live BambooHR data, verified, released, sent to a supplier, accepted, and delivered by a human operator. `birthday_dev` currently holds **0 birthday orders**.
2. **The live external-supplier B2B sign-in test is still pending a human step.** All autonomous preparation is done (the Gmail test account is an Accepted B2B guest; admin consent is granted; the app registration, redirect URI, and Key Vault secret exist; `SUPPLIER_AUTH_MODE=entra` is live and `/api/birthday/supplier/auth/config` returns `{"supplier_auth_mode":"entra"}`). The interactive Microsoft sign-in by a person, and the post-sign-in verification (identity match → `entra_object_id` link → session → portal access → isolation → logout → persona-endpoint 404), have **not** been completed.
3. **The single DEV supplier is a skeleton** — "Test Supplier" has no service locations and no catalogue items, so a detected order cannot currently be auto-assigned a supplier or a default cake.
4. **The `platform-api` `ApplicationModule` registry row for birthday** is still whatever it was; `birthday-api` hardcodes `product_status: "ACTIVE"` in its own `/summary` but does not own or flip the registry.

DijiBirthday is at the point the next iteration brief calls "DEV construction complete" — the correct next activity is to **use** it with real DEV data and find the workflow, UX, and data-shape gaps, not to rush to UAT/PROD.

---

## PART 2 — Current Architecture

DijiBirthday is two frontends + one API, inside the DijiOne Domain-Driven Distributed Modular Platform. It owns its own database (`birthday_dev`) and consumes staff data **only** through `people-api`. It holds **no** BambooHR credential and **no** cross-service database access.

```
                          ┌─────────────────────────────────────────────┐
   Internal ops user      │        Microsoft Entra ID (Dijital Team      │
   (Dijital Team staff)   │        tenant 2abce006-…)                    │
        │                 │   • internal staff  → app reg dijione-dev    │
        │  browser        │   • supplier guests → app reg                │
        ▼                 │     dijione-birthday-supplier-dev (B2B)      │
  ┌───────────┐           └───────────────┬─────────────────────────────┘
  │ shell-web │ (external ingress)        │ OIDC auth-code + PKCE
  │  /birthday│───┐                       │
  └───────────┘   │ same-origin           │
                  │ path fan-out          ▼
                  │            ┌──────────────────────┐   External cake
                  ▼            │  birthday-supplier-  │   supplier
        ┌────────────────┐     │  web (EXTERNAL       │◀──  (browser)
        │  birthday-web  │     │  ingress)            │
        │ (internal only)│     └──────────┬───────────┘
        │  6 pages       │                │  Next.js rewrites:
        └───────┬────────┘                │  /api/birthday/portal/*
                │                         │  /api/birthday/supplier/auth/*
                │ /api/birthday/*         │
                ▼                         ▼
        ┌───────────────────────────────────────────────┐
        │            birthday-api  (internal only)       │
        │  • detection engine   • 13-state machine       │
        │  • supplier domain    • dev + Entra supplier   │
        │  • order email (MOCK)    auth, both mint the    │
        │                          same session token    │
        └───┬───────────────┬───────────────────┬────────┘
            │               │                   │
            │ EmployeeDir-   │ AuditService      │ Graph email
            │ ectoryClient   │ → platform-api    │ (factory seam →
            │ (X-Internal-   │                   │  MockGraphEmailClient
            │  Token)        │                   │  in DEV)
            ▼               ▼                    ▼
   ┌──────────────┐  ┌──────────────┐    (no real email in DEV)
   │  people-api  │  │ platform-api │
   │ people_dev   │  │ platform_dev │  ┌──────────────────────┐
   │ BambooHR LIVE│  │ identity /   │  │  birthday_dev         │
   │ (read-only)  │  │ audit / RBAC │  │  (PostgreSQL Flexible │
   └──────┬───────┘  └──────────────┘  │   Server, 12 tables)  │
          │                            └──────────────────────┘
          ▼                                     ▲
   BambooHR (dijitalteam)  ─────────────────────┘  birthday-api is the
   subdomain, read-only                            only writer

   Scheduled: birthday-scan-job  (Azure Container Apps Job, cron 30 5 * * *)
              → POST birthday-api /api/birthday/internal/run-daily-scan
                (X-Internal-Token)
```

**Key architectural rules (must not be reversed):**

- Birthday **never** queries `people_dev` directly and **never** calls BambooHR directly. It calls `people-api` via `auth_client_py.EmployeeDirectoryClient`. A static guard test (`tests/test_no_direct_bamboohr_dependency.py`) enforces this.
- Birthday holds **no employee mirror/projection table**. A `people-api` outage makes the daily scan **defer** (`ScanRun.status = DEFERRED_SOURCE_UNAVAILABLE`, zero orders touched) and self-heal on the next scan. In-flight orders are unaffected because every employee fact needed downstream is **snapshotted onto the `BirthdayOrder` row at detection time**.
- **Entra authenticates; an ACTIVE `SupplierUser` authorizes.** Entra B2B membership alone grants no Birthday access.
- `supplier_id` is always taken from the server-side `SupplierUser` row, never from a request parameter.
- Birthday email goes through a factory seam and is **mock** in DEV regardless of other settings.

---

## PART 3 — Users and Roles

### Platform-level

`platform-api` owns identity, the `ApplicationModule` registry, RBAC, and the DijiOne session token. It mints an HS256 token (`iss = dijione-dev-identity`, signed with `JWT_DEV_SECRET`) carrying `module_roles` — a per-module `{role, permissions[]}` map — and, for supplier sessions, an extra `supplier` sub-claim. Every service, including `birthday-api`, decodes this token locally via `auth_client_py` and trusts the `permissions` array in it. birthday-api does **not** itself hold a role→permission table.

### DijiBirthday roles (`app/core/constants.py::BirthdayRole`)

| Role | Who | Typical permissions carried in the token |
|---|---|---|
| `BIRTHDAY_USER` | Dijital Team ops staff, read-mostly | `birthday.dashboard.read`, `birthday.orders.read` |
| `BIRTHDAY_ADMIN` | Dijital Team ops staff, full internal workflow | all `birthday.orders.*`, `birthday.suppliers.*`, `birthday.config.manage` |
| `BIRTHDAY_SUPPLIER` | External cake supplier (one per `SupplierUser`) | `birthday.portal.access`, `birthday.portal.respond` |

### DijiOne Platform Admin vs DijiBirthday Admin

They are **different things**. A **DijiOne Platform Admin** (`PLATFORM_ADMIN`) administers the platform: users, module registry, cross-module RBAC, tenants. A **DijiBirthday Admin** (`BIRTHDAY_ADMIN`) is a *module role* — it grants the internal birthday workflow (manage suppliers, manage detection config, drive orders) and nothing outside DijiBirthday. A person can hold one, both, or neither. In hosted DEV the user `madusankaweeriyasinghe20@gmail.com`'s internal identity (user id 6) was granted `BIRTHDAY_ADMIN` for internal testing; that is unrelated to the same Gmail being a supplier B2B guest.

### Supplier users

A `SupplierUser` row (see PART 10) is the application-level identity of a person at an external cake supplier. It is **never auto-created** by a sign-in. Its `status` (`ACTIVE`/`INACTIVE`) is re-checked on **every** portal request, not just at token mint.

---

## PART 4 — Internal Birthday Application (`birthday-web`), page by page

Next.js App Router, `output: "standalone"`, `basePath` served under `shell-web`'s `/birthday`. Auth chrome is the shared `@dijione/design-system` `AuthGate` → `useBirthdayScope()`; a persona/identity with no birthday module role sees an *"No DijiBirthday access"* empty state. Nav sections: **Dashboard · Upcoming Birthdays · Cake Orders · Suppliers**.

All data goes through `src/lib/api.ts` → `@dijione/auth-client`'s `request()` → `/api/birthday/*` on `birthday-api`.

### 4.1 Dashboard — `/` (`src/app/page.tsx`, ~133 lines)

- Title **"DijiBirthday Dashboard"**.
- Calls `getDashboardSummary()` → `GET /api/birthday/dashboard` (perm `birthday.dashboard.read`) and `getUpcoming(days)` → `GET /api/birthday/upcoming` (same perm).
- Shows summary metrics + an upcoming-orders list (already-detected `BirthdayOrder` rows, not the raw staff directory).

### 4.2 Upcoming Birthdays — `/upcoming` (`src/app/upcoming/page.tsx`, ~335 lines)

- Title **"Upcoming Birthdays"**, `PageHeader`.
- Calls `getUpcomingBirthdays({days, search, filter, province, sort_by, sort_direction, page, page_size})` → `GET /api/birthday/employees/upcoming-birthdays` (perm `birthday.dashboard.read`). This is the **live People-directory-derived** view (BambooHR staff with a birthday in the window), distinct from 4.1's order list.
- Filters by eligibility group (e.g. eligible / future starter), province, free-text; sortable, paginated.
- **"Run detection"** action → `runBirthdayDetection()` → `POST /api/birthday/admin/run-detection` (perm `birthday.config.manage`). Returns a scan summary (`employees_scanned`, `orders_created`, `orders_existing`, `exceptions`, `ineligible_skipped`, `errors[]`) rendered inline. This calls the **same** `detection_service.run_daily_scan` the scheduled job uses — not a duplicate path.
- Empty state **"No matches"**.

### 4.3 Cake Orders — `/orders` (`src/app/orders/page.tsx`, ~254 lines)

- Title **"Cake Orders"**, description *"Register of every cake order tracked by DijiBirthday."*
- Calls `listOrders({search, status_filter, lead_time_class, office_location, supplier_id, address_verification_status, sort_by, sort_direction, page, page_size})` → `GET /api/birthday/orders` (perm `birthday.orders.read`).
- Reads `?status_filter` / `?sort_by` from the URL (deep-linkable from the dashboard).
- Sortable columns, filter bar, pagination. Empty state **"No orders found"**.
- Row click → `/orders/{id}`.

### 4.4 Order detail — `/orders/[id]` (`src/app/orders/[id]/page.tsx` → `src/components/birthday/OrderDetail.tsx`, ~813 lines)

The internal workflow surface. Sections: **Order Details · Fulfilment Assignment · Address Verification · Special Requirements · Supplier Communications · Order History**. Mutations (all on `birthday-api`, permissions in parentheses):

| Action | Endpoint | Permission |
|---|---|---|
| Verify address (the routine checkpoint) | `POST /orders/{id}/verify` | `birthday.orders.verify` |
| Confirm-release a flagged order | `POST /orders/{id}/confirm-release` | `birthday.orders.review` |
| Hold | `POST /orders/{id}/hold` | `birthday.orders.hold_release` |
| Release | `POST /orders/{id}/release` | `birthday.orders.hold_release` |
| Cancel | `POST /orders/{id}/cancel` | `birthday.orders.cancel` |
| Send to supplier | `POST /orders/{id}/send-to-supplier` | `birthday.orders.send_supplier` |
| Resend to supplier | `POST /orders/{id}/resend` | `birthday.orders.send_supplier` |
| Update address-verification status | `PATCH /orders/{id}/address-verification` | `birthday.orders.update` |
| Update delivery address | `PATCH /orders/{id}/delivery-address` | `birthday.orders.update` |
| Add special requirement | `POST /orders/{id}/special-requirements` | `birthday.orders.update` |
| Edit order (qty, date, cake, supplier) | `PATCH /orders/{id}` | `birthday.orders.update` |
| Delete order | `DELETE /orders/{id}` | `birthday.orders.delete` |
| Resolve an order issue | `PATCH /orders/{id}/issues/{issueId}/resolve` | `birthday.orders.update` |
| Readiness check (panel) | `GET /orders/{id}/readiness` | `birthday.orders.read` |

### 4.5 Suppliers — `/suppliers` (`src/app/suppliers/page.tsx`, ~305 lines)

- Title **"Suppliers"**, **"New Supplier"** action (modal → `createSupplier()` → `POST /api/birthday/suppliers`, perm `birthday.suppliers.manage`).
- `listSuppliers({search, status_filter, sort_by, sort_direction, page, page_size})` → `GET /api/birthday/suppliers` (perm `birthday.suppliers.read`).
- Empty state **"No suppliers found"**.

### 4.6 Supplier detail — `/suppliers/[id]` (`src/app/suppliers/[id]/page.tsx` → `src/components/birthday/SupplierDetail.tsx`, ~709 lines)

Sections: **Supplier Details · Locations Served · Catalogue · Supplier Users · Internal Notes**. Mutations (perm `birthday.suppliers.manage` unless noted):

| Action | Endpoint |
|---|---|
| Edit supplier / change status | `PATCH /suppliers/{id}` |
| Add location served | `POST /suppliers/{id}/locations` |
| Add catalogue item | `POST /suppliers/{id}/catalogue` |
| Edit catalogue item | `PATCH /suppliers/{id}/catalogue/{itemId}` |
| List / add / edit supplier users | `GET·POST·PATCH /suppliers/{id}/users` |

> **This page is where a `SupplierUser` is created** — the deliberate internal action that is the prerequisite for that person ever getting portal access (PART 11).

### Test coverage (`birthday-web`)

Only `src/app/__tests__/birthday-shell.test.tsx` (2 tests) exists — it verifies the shell renders the login screen without a token and the chrome with one. The individual pages have **no** component tests in `birthday-web`; their behaviour is covered indirectly by `birthday-api`'s endpoint tests.

---

## PART 5 — Supplier Portal (`birthday-supplier-web`), page by page

Next.js App Router, **external ingress**, `output: "standalone"`. It talks only to `/api/birthday/portal/*` and `/api/birthday/supplier/auth/*` (Next.js rewrites in `next.config.ts` proxy both to `birthday-api`). It never touches the internal `/orders` or `/suppliers` paths.

Session token lives in `sessionStorage` key `dijibirthday-supplier-token`, managed by `src/lib/supplier-auth.tsx` (`SupplierAuthProvider` + `useSupplierAuth()` via `useSyncExternalStore`, cross-tab event `dijibirthday-supplier-token-change`). `src/app/app-shell.tsx`: no token → `<LoginScreen/>`; token → portal chrome (header *"DijiBirthday · by Dijital Team / Supplier Portal"*, nav **Dashboard · Orders**, **Sign out** → `setToken(null)`).

### 5.1 Login screen — `src/app/login-screen.tsx`

- Fetches `getSupplierAuthConfig()` → `GET /api/birthday/supplier/auth/config` → `{supplier_auth_mode}`.
- `supplier_auth_mode === "entra"` → **`<EntraSignIn/>`**: a framed *"Sign in with Microsoft"* link to `/login`. **No "development mode" wording.**
- `supplier_auth_mode === "dev"` → **`<DevPersonaPicker/>`**: lists seeded `SupplierUser` personas (`GET /api/birthday/internal/dev/supplier-users`), copy *"Local development mode — pick a supplier persona below."*
- Config fetch error → falls back to the persona picker.

### 5.2 Entra sign-in flow (hosted DEV)

1. `GET /login` (`src/app/login/route.ts`) → server calls `birthday-api` `GET /api/birthday/supplier/auth/login-url` → gets `{authorize_url, flow_token}` (PKCE S256, scope `openid profile email`, `state`, `nonce`). Sets httpOnly cookie `dijibirthday_supplier_flow` (secure, sameSite lax, maxAge 600) → 302 to Microsoft.
2. Microsoft → `GET /api/auth/callback` (`src/app/api/auth/callback/route.ts`) with `?code&state` → server reads the flow cookie → `POST /api/birthday/supplier/auth/token {code, state, flow_token}` → `birthday-api` does the server-side code exchange, verifies the `id_token` (RS256/JWKS, iss/aud/tid/nonce/exp), resolves the `SupplierUser`, mints the session token. Cookie deleted in `finally`. **Token is written to `sessionStorage` by a tiny bootstrap page and never appears in a URL.** `403` → generic *"not authorised"* screen with a Back link.

### 5.3 Dashboard — `/` (`src/app/page.tsx`)

- `getPortalDashboard(token)` → `GET /api/birthday/portal/dashboard` (perm `birthday.portal.access`).
- Metric cards: **New orders to accept · Due today · Due tomorrow · Overdue · Out for delivery · Open problems**; card **"Completed today"**; **"View all orders →"**.
- Every count is computed server-side filtered by `supplier_id` from the token's server-resolved scope.

### 5.4 Orders list — `/orders` (`src/app/orders/page.tsx`)

- Title **"Your Orders"**, copy *"Cake orders assigned to your business. Only fulfilment details are shown here."*
- `listPortalOrders(token, {search, page, page_size})` → `GET /api/birthday/portal/orders` (perm `birthday.portal.access`, `page_size` capped at 50).
- Columns: Reference · Recipient · Delivery Date · Location · Product · Qty · Address Verified · Status. Empty state **"No orders yet"**.
- The `SupplierOrderView` DTO (`order_service.to_supplier_view`) exposes **only** fulfilment fields; the delivery address is withheld until `address_verification_status == VERIFIED`.

### 5.5 Order detail — `/orders/[id]` (`src/app/orders/[id]/page.tsx`)

- `getPortalOrder(token, id)` → `GET /api/birthday/portal/orders/{id}` (perm `birthday.portal.access`; 404 if the order is not this supplier's).
- **Accept** (only when status `SENT_TO_SUPPLIER`) → `acceptPortalOrder` → `POST /portal/orders/{id}/accept` (perm `birthday.portal.respond`). Merged acknowledge+confirm — one click = *"we have it and we will fulfil it"*.
- **Status buttons** driven by `SUPPLIER_DRIVABLE_TARGETS` imported from `@dijione/contracts` (derived from the backend `order_status_service.SUPPLIER_DRIVABLE`, not a hand-copied table): Start Preparing → Out for Delivery → Mark Delivered; plus Request Change / Unable to Fulfil. → `updatePortalOrderStatus` → `PATCH /portal/orders/{id}/status` (perm `birthday.portal.respond`).
- **Report a Problem** modal (type: Change request / Cannot fulfil / Delivery problem / Other + detail) → `raisePortalIssue` → `POST /portal/orders/{id}/issues` (perm `birthday.portal.respond`).
- Fulfilment Details card: delivery date, product, quantity, address-verified flag, delivery address (only if verified), special instructions.

### 5.6 `SUPPLIER_AUTH_MODE` — local vs hosted

| | Local dev | Hosted Azure DEV (now) |
|---|---|---|
| `SUPPLIER_AUTH_MODE` | `dev` (default) | **`entra`** (verified live: `/api/birthday/supplier/auth/config` → `{"supplier_auth_mode":"entra"}`) |
| Sign-in UI | seeded-persona picker | "Sign in with Microsoft" |
| `/api/birthday/internal/dev/supplier-*` | available | **404** |
| Entra config needed | none | `SUPPLIER_ENTRA_*` env + `birthday-supplier-entra-secret-dev` Key Vault secret |

### 5.7 Status of the live B2B test — **PENDING (human step not performed)**

| Step | State |
|---|---|
| App registration `dijione-birthday-supplier-dev` (appId `30e36193-f0e4-40d5-875b-db1ef6a3f2b0`), single-tenant, PKCE-only, redirect `…/api/auth/callback`, delegated `openid profile email`, admin consent granted, `appRoleAssignmentRequired=false` | **Done** |
| Key Vault secret `birthday-supplier-entra-secret-dev` | **Exists** (value not inspected) |
| Bicep `supplierAuthMode='entra'` + env wired; `birthday-api` deployed with `SUPPLIER_AUTH_MODE=entra`, `SUPPLIER_ENTRA_CLIENT_ID` set; `/login-url` returns HTTP 200 live | **Done / verified** |
| B2B guest for `madusankaweeriyasinghe20@gmail.com` in the Dijital Team tenant | **Exists + Accepted**, oid `5847f827-d893-46fc-af54-0214a1619c21` |
| `SupplierUser` id 1 (`madusankaweeriyasinghe20@gmail.com`, "Kumar Sangakkara", ACTIVE, SUPPLIER_ADMIN, supplier_id 1) | **Exists**, `entra_object_id = NULL` (never linked because no one has signed in yet) |
| **Interactive Microsoft sign-in by a person** | **NOT DONE** |
| Post-sign-in verification: Entra auth → `SupplierUser` match → `entra_object_id` stamped → session issued → portal access → supplier isolation → logout → persona endpoints 404 | **NOT DONE** |

There is **no automated substitute** for the interactive step; it requires a human at a browser completing the Microsoft prompt.

---

## PART 6 — Complete Business Workflow (end to end)

```
[1] Employee exists in BambooHR (dijitalteam), has a birth date + work email
        │  people-api syncs BambooHR → people_dev (daily people-sync-job; read-only)
        ▼
[2] birthday-scan-job fires (cron 30 5 * * * UTC) → POST birthday-api
    /api/birthday/internal/run-daily-scan  (X-Internal-Token)
        │   OR an ops user clicks "Run detection" on /upcoming
        ▼
[3] detection_service.run_daily_scan:
      • opens a ScanRun row (trigger SCHEDULED | MANUAL)
      • fetches active employees via EmployeeDirectoryClient → people-api
      •   people-api down?  →  ScanRun.status = DEFERRED_SOURCE_UNAVAILABLE,
      •                        0 orders, nothing touched, self-heals next run
      • per employee:
          - map + compute next birthday occurrence (Feb 29 → Mar 1 off-leap)
          - inside scan window?  (-lookback .. +lookahead days, default -1..+14)
          - compute_eligibility → FUTURE_STARTER / INACTIVE / ENDED / MISSING_* / ELIGIBLE
          - classify lead time → NORMAL / SHORT_NOTICE / URGENT
          - resolve supplier for office (sole active → by office location → default → none)
          - resolve default cake (single default → single item → none → NO_DEFAULT_CAKE)
          - verify_by = occurrence_date − (supplier lead_time_days + verify_buffer_days)
          - determine_initial_status:
                no work_email      → REQUIRES_ATTENTION / MISSING_EMAIL
                no supplier        → REQUIRES_ATTENTION / NO_SUPPLIER
                items but no default→ REQUIRES_ATTENTION / NO_DEFAULT_CAKE
                days_remaining ≥ lead → PENDING_VERIFICATION
                else               → ON_HOLD
          - create_or_get_order  (UniqueConstraint(employee_id, birthday_year) → idempotent)
          - SNAPSHOT employee facts onto the order row (name, email, address, office…)
          - db.commit() per employee; on error db.rollback() and continue
        ▼
[4] Internal ops user opens /orders, opens an order in REQUIRES_ATTENTION or
    PENDING_VERIFICATION:
      • fixes exceptions (assign supplier, pick cake, correct address, set date)
      • "Verify address"  (POST /orders/{id}/verify)  ← THE routine human checkpoint
            standard order      → auto-released → SENT_TO_SUPPLIER (email attempt)
            non-standard/flagged → REQUIRES_REVIEW → ops "Confirm release"
                                   (POST /orders/{id}/confirm-release) → SENT_TO_SUPPLIER
        ▼
[5] order_email_service sends the supplier email  → get_email_client()
      DEV: MockGraphEmailClient (nothing actually sent), a SupplierCommunication
      row is written; success → status SENT_TO_SUPPLIER, failure → REQUIRES_ATTENTION
        ▼
[6] Supplier signs in to the Supplier Portal (Entra B2B in hosted DEV),
    sees the order as "New order to accept":
      • Accept          → CONFIRMED   (accepted_at set)
      • Start Preparing → PREPARING   (preparing_at)
      • Out for Delivery→ OUT_FOR_DELIVERY (out_for_delivery_at)
      • Mark Delivered  → DELIVERED   (delivered_at)
      • (or) Request Change / Unable to Fulfil / Report a Problem → OrderIssue,
             status CHANGE_REQUESTED / UNABLE_TO_FULFIL / REQUIRES_ATTENTION
        ▼
[7] auto_complete: DELIVERED → COMPLETED  (system actor; no internal user action
    exists for this on purpose)
        ▼
[8] Every transition in [4]–[7] wrote an OrderEvent + an AuditService.log
    ("birthday.order.status_change"); the order carries its full history.
```

---

## PART 7 — Order State Machine (extracted from `app/services/order_status_service.py`)

**14 statuses** (`app/core/constants.py::OrderStatus`): `PENDING_VERIFICATION`, `REQUIRES_REVIEW`, `REQUIRES_ATTENTION`, `ON_HOLD`, `SENT_TO_SUPPLIER`, `CHANGE_REQUESTED`, `CONFIRMED`, `PREPARING`, `OUT_FOR_DELIVERY`, `DELIVERED`, `COMPLETED`, `UNABLE_TO_FULFIL`, `CANCELLED` (+ legacy `DRAFT/READY_FOR_APPROVAL/APPROVED/PLANNED/REJECTED/SUPPLIER_REVIEW` retired — no persisted data to migrate).

**`ALLOWED_TRANSITIONS`:**

| From | To |
|---|---|
| `PENDING_VERIFICATION` | `REQUIRES_REVIEW`, `SENT_TO_SUPPLIER`, `ON_HOLD`, `REQUIRES_ATTENTION`, `CANCELLED` |
| `REQUIRES_REVIEW` | `SENT_TO_SUPPLIER`, `ON_HOLD`, `REQUIRES_ATTENTION`, `CANCELLED` |
| `REQUIRES_ATTENTION` | `PENDING_VERIFICATION`, `SENT_TO_SUPPLIER`, `ON_HOLD`, `CANCELLED`, `REQUIRES_ATTENTION` |
| `ON_HOLD` | `PENDING_VERIFICATION`, `REQUIRES_REVIEW`, `SENT_TO_SUPPLIER`, `CANCELLED` |
| `SENT_TO_SUPPLIER` | `CONFIRMED`, `CHANGE_REQUESTED`, `UNABLE_TO_FULFIL`, `ON_HOLD`, `REQUIRES_ATTENTION`, `CANCELLED` |
| `CHANGE_REQUESTED` | `SENT_TO_SUPPLIER`, `CANCELLED` |
| `CONFIRMED` | `PREPARING`, `UNABLE_TO_FULFIL`, `CANCELLED` |
| `PREPARING` | `OUT_FOR_DELIVERY`, `UNABLE_TO_FULFIL`, `CANCELLED` |
| `OUT_FOR_DELIVERY` | `DELIVERED`, `REQUIRES_ATTENTION`, `CANCELLED` |
| `DELIVERED` | `COMPLETED` |
| `UNABLE_TO_FULFIL` | `REQUIRES_ATTENTION` |
| `CANCELLED` | *(terminal)* |
| `COMPLETED` | *(terminal)* |

**`SUPPLIER_DRIVABLE`** (the only transitions a supplier token may cause): `SENT_TO_SUPPLIER → {CONFIRMED, CHANGE_REQUESTED, UNABLE_TO_FULFIL}`; `CONFIRMED → {PREPARING}`; `PREPARING → {OUT_FOR_DELIVERY}`; `OUT_FOR_DELIVERY → {DELIVERED}`.
**`SUPPLIER_VISIBLE_STATUSES`** includes terminal states so a cancellation shows as a tombstone in the portal.

`transition(db, order, to_status, *, actor_id, actor_type, detail, event_type="STATUS_CHANGE", audit_service)` raises `InvalidTransitionError` on a disallowed edge, writes an `OrderEvent`, and best-effort `AuditService.log`. Helpers: `hold`, `release` (defaults to `PENDING_VERIFICATION`), `cancel`, `auto_complete` (`DELIVERED → COMPLETED`, system actor).

---

## PART 8 — Birthday Detection Engine (`app/services/detection_service.py`, `eligibility_service.py`)

- **Idempotency:** `UniqueConstraint(employee_id, birthday_year)` on `birthday_orders` + `create_or_get_order` + per-employee commit. Re-running a scan creates nothing new for an already-detected employee/year.
- **Occurrence:** `compute_next_birthday_occurrence(birth_month, birth_day, today)` — Feb 29 resolves to Mar 1 in a non-leap occurrence year.
- **Scan window:** `-window_lookback_days ≤ days_remaining ≤ window_lookahead_days` (config defaults `1` / `14`).
- **Eligibility order** (`compute_eligibility`): `MISSING_BIRTHDAY` → `INVALID_EMPLOYEE_DATA` → `INACTIVE_EMPLOYEE` (status ≠ "Active") → `MISSING_HIRE_DATE` → `FUTURE_STARTER` (hire_date > occurrence) → `EMPLOYMENT_ENDED` (termination_date < occurrence) → `ELIGIBLE`. `FUTURE_STARTER` does **not** count toward the exception total.
- **Lead-time class** (`classify_lead_time`): `NORMAL` / `SHORT_NOTICE` / `URGENT` from config thresholds (`10` / `5` / `2` days).
- **Supplier resolution** (`resolve_supplier_for_office`): sole active supplier → by office location → platform default → `None` (→ `NO_SUPPLIER` exception).
- **Cake resolution** (`resolve_default_catalogue_item`): no items → `None`; exactly one default → it; exactly one item → it; ambiguous → `None` (→ `NO_DEFAULT_CAKE`).
- **Initial status** (`determine_initial_status`): see PART 6 step [3].
- **Source outage:** `EmployeeSourceUnavailableError` → `ScanRun.status = DEFERRED_SOURCE_UNAVAILABLE`, returns zeros, touches nothing, self-heals next scan.
- **Config** (`birthday_detection_configs`, single row): `normal/short_notice/urgent` thresholds `10/5/2`, `window_lookback/lookahead` `1/14`, `default_quantity 1`, `verify_buffer_days 2`, `acknowledgement_sla_hours 24`, `auto_release_enabled true`. Editable at `/config` (perm `birthday.config.manage`).

---

## PART 9 — People / BambooHR Integration Boundary

- **Owner of BambooHR:** `people-api` only (`people_dev`, `INTEGRATIONS_MODE=live`, `BAMBOOHR_SUBDOMAIN=dijitalteam`, read-only). Confirmed live in DEV.
- **Birthday's consumption:** `app/integrations/people_source/http_adapter.py::PeopleApiEmployeeSource` wraps `auth_client_py.EmployeeDirectoryClient(base_url=people_api_url, internal_secret=internal_service_secret, timeout=5.0, caller="birthday-api")`. Calls `list_employees(active_only=True)` / `get_employee(id)`. `_to_record` maps `bamboohr_id`→id, plus `employee_number`, `full_name`, `work_email`, `birth_month`, `birth_day`, `department`, `office_location`, `employment_status`, `hire_date`, `termination_date`, address fields. `httpx.HTTPError` → `EmployeeSourceUnavailableError`.
- **Factory:** `app/integrations/factory.py::get_employee_source()` → `MockEmployeeSource()` if `integrations_mode == "mock"`, else `PeopleApiEmployeeSource()`. **`birthday-api` runs `INTEGRATIONS_MODE=mock` in hosted DEV** (verified live) — so detection currently reads **mock** employees, not live People data, even though `people-api` itself is live. This is a deliberate DEV setting, and the single most important thing to flip for a real DEV validation run (see PART 17 / PART 22).
- **No** BambooHR credential, **no** employee mirror table, **no** cross-service DB access in `birthday-api`. Static guard: `tests/test_no_direct_bamboohr_dependency.py`.
- **`/health/deep`** reports `people_source: "ok" | "degraded"` (non-fatal — a `people-api` cold start shows `degraded` by design).

---

## PART 10 — Supplier Domain

Models (`app/models/`):

| Table | Purpose / notable columns |
|---|---|
| `suppliers` | `name`, `status` (default `ACTIVE`), primary + escalation contacts, `lead_time_days`, `working_days`, `cutoff_time`, `notes` (internal-only), `is_default` |
| `supplier_users` | `supplier_id` FK CASCADE, `email` unique, `full_name`, `role` (`SUPPLIER_USER`/`SUPPLIER_ADMIN`), `status` (default `ACTIVE`), **`entra_object_id`** `String(64)` nullable unique — "Microsoft Entra ID B2B guest join key" |
| `supplier_catalogue_items` | `name`, `description`, `is_active`, `is_default` |
| `supplier_locations` | `office_location` unique, `is_primary` |
| `supplier_communications` | `order_id` FK CASCADE, `supplier_id`, `direction`, `channel` (`EMAIL`), `subject`, `body`, `sent_at`, `message_id`, `status`, `retry_count`, `last_error` |

**Live DEV data (`birthday_dev`):** 1 supplier — **"Test Supplier"** (ACTIVE, lead_time 7 days, Mon–Fri, cutoff 12:00, no escalation contact, **no locations, no catalogue items**). 1 supplier user — id 1, `madusankaweeriyasinghe20@gmail.com`, "Kumar Sangakkara", ACTIVE, SUPPLIER_ADMIN, `entra_object_id = NULL`, supplier_id 1. 0 supplier communications.

**Consequence:** because Test Supplier has no locations and no catalogue items, `resolve_supplier_for_office` may still return it only if it is the *sole active* supplier (it is), but `resolve_default_catalogue_item` returns `None` → every detected order would land in `REQUIRES_ATTENTION / NO_DEFAULT_CAKE`. A real DEV run needs at least one catalogue item (ideally marked default) and, for office-routing tests, at least one `supplier_locations` row.

Internal management endpoints: `GET/POST /api/birthday/suppliers`, `GET/PATCH /api/birthday/suppliers/{id}`, `.../locations`, `.../catalogue`, `.../catalogue/{itemId}`, `.../users`, `.../users/{userId}` (read = `birthday.suppliers.read`, write = `birthday.suppliers.manage`).

---

## PART 11 — Authentication & Authorization (both trust models)

### 11.1 Internal users (`birthday-web`)

Standard DijiOne flow. `shell-web`/`platform-api` in hosted DEV run `AUTH_MODE=entra` (real Microsoft Entra sign-in for Dijital Team staff, OIDC auth-code + PKCE, server-side code exchange, RS256/JWKS id_token verification). `platform-api` then mints the HS256 DijiOne session token (`iss = dijione-dev-identity`). `birthday-api` decodes it locally via `auth_client_py.make_get_claims(secret=jwt_dev_secret, algorithm="HS256")`.

- `get_birthday_scope` reads `claims.module("birthday")`; 403 if absent.
- `require_birthday_permission(key)` → 403 unless `key` is in the module claim's `permissions` frozenset.
- `birthday-api` trusts the `permissions` array in the verified token; the role→permission mapping lives in `platform-api`'s identity layer.

### 11.2 Supplier users (`birthday-supplier-web`) — two independent layers

**Layer 1 — Entra authenticates.** In `entra` mode, `app/core/supplier_entra.py::SupplierEntraVerifier` validates the `id_token`: RS256 via JWKS, `audience = supplier_entra_client_id`, `issuer = https://login.microsoftonline.com/<tid>/v2.0`, requires `["exp","iss","aud"]`, checks `tid` match and `nonce` match. State + PKCE are checked in `app/api/routes/supplier_auth_entra.py`. A B2B guest's rewritten `#EXT#` UPN is **never** treated as an email.

**Layer 2 — an ACTIVE `SupplierUser` authorizes.** `app/services/supplier_auth.py::resolve_supplier_user(db, claims)`:
1. match `SupplierUser.entra_object_id == oid` → use it;
2. else `_email_from_claims` (prefers the verified `email` claim; rejects `#EXT#`; accepts `preferred_username`/`upn` only if a plain `user@domain`) → `func.lower(SupplierUser.email) == email`; if found **and** `entra_object_id is None` → **stamp the oid and commit** (first-login link);
3. no match → `raise SupplierAccessRefusedError` → generic **403** *"Your account is not authorised for the DijiBirthday supplier portal."*
4. `status != "ACTIVE"` → same generic 403.

**`SupplierUser` is never auto-created.** Then `mint_supplier_session_token(supplier_user)` → HS256, `iss dijione-dev-identity`, 8 h, `module_roles = {birthday: {role: BIRTHDAY_SUPPLIER, permissions: ["birthday.portal.access","birthday.portal.respond"]}}`, `supplier = {supplier_id, supplier_user_id}`.

**Per-request re-check** (`app/api/deps.py::get_supplier_scope`): re-loads `SupplierUser` by `claims.supplier.supplier_user_id`; 403 if missing or `status != "ACTIVE"`; **`supplier_id` is taken from that row, never the claim or the URL**. So deactivating a `SupplierUser` kills portal access on the next request, not at token expiry, and a supplier cannot read another supplier's order (`get_for_supplier(order_id, supplier_id=scope.supplier_id)` → 404).

**Dev mode** (`SUPPLIER_AUTH_MODE=dev`): `app/api/routes/dev_auth.py` offers `GET /api/birthday/internal/dev/supplier-users` + `POST /api/birthday/internal/dev/supplier-login {supplier_user_id}`. Both paths (`dev_auth` and `supplier_auth_entra`) end at the same `mint_supplier_session_token`, so `SupplierScope` / isolation are identical. In `entra` mode these routes return **404** (not 403 — deliberately non-discoverable), gated on `settings.dev_supplier_auth_enabled` (`supplier_auth_mode == "dev"`), **not** on `APP_ENV`.

`SUPPLIER_ENTRA_CLIENT_SECRET` is resolved from Key Vault (`birthday-supplier-entra-secret-dev`) via the shared managed identity; it never reaches the browser bundle.

---

## PART 12 — Email / Notifications

| Capability | State |
|---|---|
| Supplier order email (order → supplier) | **IMPLEMENTED, MOCKED in DEV.** `order_email_service.render_supplier_email` + `get_email_client()`; `EMAIL_SENDING_MODE=mock` (verified live) → `MockGraphEmailClient` — nothing is sent. A `supplier_communications` row is still written; success → `SENT_TO_SUPPLIER`, failure → `REQUIRES_ATTENTION` + `EMAIL_FAILED` `OrderEvent` + `retry_count` bump. `resend` / `auto_release` / `confirm_release` all route through the same `_send`. |
| Real Microsoft Graph email | **CODE EXISTS, NOT ENABLED.** `GraphEmailClient` + `GRAPH_TENANT_ID/CLIENT_ID/CLIENT_SECRET/SENDER_MAILBOX` settings; a deliberately independent Graph app-registration seam. `EMAIL_SENDING_MODE` is independent of `INTEGRATIONS_MODE`; flipping it to real Graph email is explicitly **out of DEV scope**. |
| Inbound supplier replies | **RESERVED.** `CommunicationDirection.INBOUND`, `CommunicationStatus.REPLIED` exist in constants; no ingestion path implemented. |
| Teams channel | **RESERVED** in `CommunicationChannel` (`TEAMS`); not implemented. |
| Ops notifications (scan failure, exceptions) | **PARTIAL.** `app/services/notification_service.py` exists; the scheduled-sync failure/observability wiring is lighter than the DijiOne source-sync contract's "operational warning to TA_MANAGER/admin". Detection deferral is recorded on `ScanRun` but not proactively pushed. |
| Audit | **IMPLEMENTED.** `AuditService.log` → `platform-api` (best-effort) on every status change and material mutation. |

---

## PART 13 — Database (`birthday_dev`, PostgreSQL Flexible Server)

**12 model tables** (`app/models/`): `birthday_order`, `detection_config`, `order_event`, `order_issue`, `order_sequence`, `scan_run`, `special_requirement`, `supplier`, `supplier_catalogue_item`, `supplier_communication`, `supplier_location`, `supplier_user`.

**11 Alembic migrations** — chain and current head:

```
dcde696849a5  birthday_api_initial_schema
cb458018416c  add address_verification_status
a1b2c3d4e5f6  add employee_number to birthday_orders
b2c3d4e5f6a7  add delivery/catalogue/entra fields
c3d4e5f6a7b8  add role to supplier_users
f3a91c7b2e04  add delivery_address to birthday_orders
e7f2a0b1c9d3  add approval provenance to birthday_orders
f8b3d1a4c206  add is_default to suppliers
a1c9e3f5b7d2  semi-automation state machine
b2d4f6a8c1e3  scan_run status
c4f6a8b0d2e4  drop_phase3_mock_orders          ← HEAD
```

`c4f6a8b0d2e4` deletes `birthday_orders WHERE employee_id LIKE 'bhr-10%' AND status='REQUIRES_ATTENTION'` (guarded ≤ 25 rows, Postgres-only, no-op on SQLite) — the Phase-3 mock-order cleanup. **DB head confirmed = `c4f6a8b0d2e4`** (migrate-birthday-api job image `sha256:aed4bf05…`, args `alembic upgrade head`).

**`birthday_orders`** (~40 columns) key fields: `order_reference` unique, `employee_id` (idempotency key), `employee_number` (business-facing, nullable), `employee_name`/`employee_email` (**snapshot**), `birthday_date`/`birthday_year`, `status` (default `PENDING_VERIFICATION`), `exception_reason`, `verify_by`, `address_verification_status` (default `NOT_CHECKED`), `delivery_address_*` snapshot + `delivery_address_source` (`BAMBOOHR`|`MANUAL_CORRECTION`), `supplier_id` FK nullable, `delivery_date`, `catalogue_item_id` FK, `quantity`, `released_at/by`, `review_confirmed_at/by`, `accepted_at`/`preparing_at`/`out_for_delivery_at`/`delivered_at`/`completed_at`, `requires_admin_review`, `retry_count`, `created_by`. `UniqueConstraint(employee_id, birthday_year)`.

**Live data state (`birthday_dev`, read via inspection earlier this scope):** 0 birthday orders · 0 supplier communications · 1 supplier · 1 supplier user · 0 scan-run rows of note. No PII at rest.

---

## PART 14 — API Inventory (`birthday-api`, grouped)

Base: internal ingress only. All `/api/birthday/*`. Permission in parentheses.

**Module metadata / health**
- `GET /health`, `GET /health/deep` (db + migration revision/drift + `integrations_mode` + `email_sending_mode` + `people_source` reachability) — no auth
- `GET /api/birthday/metadata`, `GET /api/birthday/summary` — no auth (DijiOne Home card); `summary` hardcodes `product_status:"ACTIVE"`
- `GET /api/birthday/whoami` — any valid session token

**Dashboard (`birthday.dashboard.read`)**
- `GET /api/birthday/dashboard`
- `GET /api/birthday/upcoming`
- `GET /api/birthday/employees/upcoming-birthdays` (live People-directory-derived)

**Orders — internal (`birthday.orders.*`)**
- `GET /api/birthday/orders` · `GET /orders/{id}` · `GET /orders/{id}/readiness` · `GET /orders/{id}/issues` (`.read`)
- `POST /orders` (`.create`) · `PATCH /orders/{id}` (`.update`) · `DELETE /orders/{id}` (`.delete`)
- `POST /orders/{id}/verify` (`.verify`) · `POST /orders/{id}/confirm-release` (`.review`)
- `POST /orders/{id}/hold` · `/release` (`.hold_release`) · `POST /orders/{id}/cancel` (`.cancel`)
- `POST /orders/{id}/send-to-supplier` · `/resend` (`.send_supplier`)
- `PATCH /orders/{id}/address-verification` · `/delivery-address` · `POST /orders/{id}/special-requirements` · `POST /orders/{id}/issues` · `PATCH /orders/{id}/issues/{issueId}/resolve` (`.update`)

**Suppliers — internal**
- `GET /api/birthday/suppliers` · `GET /suppliers/{id}` · `.../locations` · `.../catalogue` · `.../users` (`birthday.suppliers.read`)
- `POST /suppliers` · `PATCH /suppliers/{id}` · `POST/PATCH .../catalogue[/{itemId}]` · `POST .../locations` · `POST/PATCH .../users[/{userId}]` (`birthday.suppliers.manage`)

**Detection config / admin (`birthday.config.manage`)**
- `GET/PATCH /api/birthday/config`
- `POST /api/birthday/admin/run-detection` · `GET /api/birthday/admin/scan-runs`

**Supplier Portal (`birthday.portal.access` / `birthday.portal.respond`)**
- `GET /api/birthday/portal/dashboard` · `GET /portal/orders` · `GET /portal/orders/{id}` · `GET /portal/orders/{id}/issues` (`.access`)
- `POST /portal/orders/{id}/accept` · `PATCH /portal/orders/{id}/status` · `POST /portal/orders/{id}/issues` (`.respond`)

**Supplier auth**
- `GET /api/birthday/supplier/auth/config` — always available
- `GET /api/birthday/supplier/auth/login-url` — 501 if not `entra`/unconfigured; 200 + PKCE otherwise
- `POST /api/birthday/supplier/auth/token` — code→session; 400 state mismatch / 401 bad token or rejected code / 403 no ACTIVE SupplierUser

**Internal service-to-service (`X-Internal-Token`)**
- `POST /api/birthday/internal/run-daily-scan` · `GET /api/birthday/internal/scan-runs[/{run_id}]`

**Dev-only (404 unless `SUPPLIER_AUTH_MODE=dev`)**
- `GET /api/birthday/internal/dev/supplier-users` · `POST /api/birthday/internal/dev/supplier-login`

---

## PART 15 — Azure DEV State (read-only inspection, 2026-09-09)

Subscription **"Dijital Team IT Production"**, RG `rg-dijione-dev`, ACA env `livelypebble-890e141a.southeastasia`.

**Container Apps**

| App | Image digest | Ingress | min/max replicas |
|---|---|---|---|
| `birthday-api` | `crdijionenonprod.azurecr.io/dijione/birthday-api@sha256:aed4bf05e3b8c26a5e8e971c69e6d4ec93c6674c35e0d8e5e45a8dc24bc0d588` | internal | 0 / 1 |
| `birthday-web` | `…/birthday-web@sha256:b555b230973ef8ab28b95ebc10071e232696cc22064c979645c62bec379f3b75` | internal | 0 / 1 |
| `birthday-supplier-web` | `…/birthday-supplier-web@sha256:78aac8960fcb52741f2076262bf1a2d9331cb5e47b368f1710476d7ec15b8998` | **external** (`birthday-supplier-web.livelypebble-890e141a.southeastasia.azurecontainerapps.io`) | 0 / 1 |

**`birthday-api` runtime env** (verified): `APP_ENV=development`, `INTEGRATIONS_MODE=mock`, `EMAIL_SENDING_MODE=mock`, `SUPPLIER_AUTH_MODE=entra`, `SUPPLIER_ENTRA_CLIENT_ID=30e36193-f0e4-40d5-875b-db1ef6a3f2b0`, `PEOPLE_API_URL=http://people-api`.

**Container Apps Jobs**: `birthday-scan-job` — cron **`30 5 * * *`** (05:30 UTC daily), same image digest, invokes the internal daily-scan endpoint. `migrate-birthday-api` — manual/deploy trigger, `alembic upgrade head`.

**Key Vault (`kv-dijione-dev`)** birthday-related secret **names**: `database-url-birthday`, `birthday-supplier-entra-secret-dev`. (Values not read.)

**Live endpoint checks** (through the external supplier-web): `GET /api/birthday/supplier/auth/config` → `{"supplier_auth_mode":"entra"}`; `GET /api/birthday/supplier/auth/login-url` → **HTTP 200**.

**`/health/deep`** (from earlier inspection this scope): `status: healthy`, `integrations_mode: mock`, `email_sending_mode: mock`, `people_source: ok|degraded` depending on `people-api` warmth.

**Bicep** (`deploy/bicep/main.dev.bicepparam`): `deployBirthday = true`, `supplierAuthMode = 'entra'`, `supplierEntraTenantId = 2abce006-6ea2-4675-b39d-33e0a54c46c7`, `supplierEntraClientId = 30e36193-…`, `supplierPublicBaseUrl = https://birthday-supplier-web.livelypebble-890e141a.southeastasia.azurecontainerapps.io`. All DEV services `minReplicas = {}` (→ 0), `maxReplicasDefault = 1`, `containerCpu = 0.25`, `containerMemory = 0.5Gi`.

> **Discrepancy flagged:** a prior working summary recorded the deployed `birthday-api` image (`aed4bf05…`) as built at commit `3982034`, *before* the supplier Entra B2B work (`610ed61`), and therefore "not rebuilt for supplier Entra". The **live service contradicts that**: `/api/birthday/supplier/auth/config` and `/login-url` respond exactly as the `610ed61` code specifies (the routes would 404 entirely if absent). **Reported state: the deployed `birthday-api` contains the Entra B2B supplier-auth implementation and it is serving in hosted DEV.** The exact commit that produced digest `aed4bf05…` is **NOT VERIFIED** (no image→commit build-record file exists in the repo).

---

## PART 16 — Test Coverage

| Suite | Count | Result |
|---|---|---|
| `birthday-api` (`pytest`) | **195** | all pass (136 s) |
| `birthday-supplier-web` (`vitest`) | **6** | all pass — `login-screen.test.tsx` (3: entra→"Sign in with Microsoft" `href="/login"`, no dev wording, no persona fetch; dev→persona picker; config-error→persona fallback), `app-shell.test.tsx` (3: no token→login, token→chrome, sign out→`setToken(null)`) |
| `birthday-web` (`vitest`) | **2** | all pass — `birthday-shell.test.tsx` (no token→login; token→chrome) |

**`birthday-api` behavioural coverage** (by area): detection engine (occurrence maths, window, eligibility ladder, supplier/cake resolution, initial status, idempotency, deferred-source path) · state machine (every allowed + rejected transition, supplier-drivable subset) · address verification / auto-release / confirm-release / flag classification · order email (mock send, communication row, failure → REQUIRES_ATTENTION + EMAIL_FAILED, resend) · order CRUD + issues + special requirements · supplier domain CRUD · **supplier Entra B2B** (`test_supplier_entra_auth.py`, 20: config dev/entra; login-url 501/200+PKCE; active guest + ACTIVE SupplierUser → working token + oid stamped on first login; second login matches by oid even if email changed; valid identity + no SupplierUser → 403; INACTIVE → 403; missing email+oid → 403; `#EXT#` UPN not an email → 403; wrong tenant/aud/sig/exp/nonce → 401; Entra rejects code → 401; state mismatch → 400; supplier A cannot read supplier B's order — list total 0, by-id 404) · **dev supplier auth** (`test_dev_supplier_auth.py`: persona routes 404 under `SUPPLIER_AUTH_MODE=entra`, available under `dev` even with `APP_ENV=production`; minted token resolves through the same `SupplierScope`) · static guard `test_no_direct_bamboohr_dependency.py`.

**Gaps in test coverage:** no `birthday-web` per-page/component tests; no end-to-end (browser) test of either portal; the Entra `id_token` signature path is mocked (JWKS + code exchange patched), so real-token verification is exercised only by the shared `platform-api` `EntraTokenVerifier` pattern it was copied from.

---

## PART 17 — Real DEV Data / Validation Status

| Capability | CODE EXISTS | AUTOMATED TEST PASSES | HOSTED DEV VERIFIED | REAL BUSINESS PROCESS VERIFIED |
|---|---|---|---|---|
| Birthday detection engine | ✅ | ✅ | ⚠️ deployed + job scheduled; **runs against `INTEGRATIONS_MODE=mock` employees** | ❌ no run against live BambooHR data |
| Order state machine | ✅ | ✅ | ✅ endpoints reachable | ❌ no human-driven order lifecycle |
| Internal Birthday app (6 pages) | ✅ | partial (shell only) | ✅ reachable via `shell-web /birthday` | ❌ not exercised with real orders |
| Supplier Portal pages | ✅ | ✅ (shell/login) | ✅ reachable (external ingress) | ❌ no supplier has signed in |
| Supplier dev-persona auth | ✅ | ✅ | n/a (disabled — `entra` mode) | n/a |
| Supplier Entra B2B auth | ✅ | ✅ (mocked JWKS) | ✅ config + login-url live; app reg + guest + secret ready | ❌ **interactive human sign-in pending** |
| Supplier isolation | ✅ | ✅ | ⚠️ enforced in code, not observed live | ❌ |
| Order → supplier email | ✅ | ✅ | ✅ mock path deployed | ❌ (mock only, by design) |
| People/BambooHR consumption | ✅ | ✅ | ⚠️ `people-api` live, but `birthday-api` set to `mock` | ❌ |
| Audit logging | ✅ | ✅ | ⚠️ best-effort to `platform-api` | ❌ not reviewed against real events |

**Bottom line:** everything is *code-complete and test-green*; almost nothing has been *exercised as a real business process in hosted DEV*. The two settings standing between "deployed" and "really validated" are `birthday-api INTEGRATIONS_MODE` (`mock` → `live`) and the pending human Entra sign-in.

---

## PART 18 — What Is Complete

- Full birthday-detection engine with idempotency, eligibility ladder, lead-time classification, supplier/cake resolution, exception typing, and graceful source-outage deferral + self-heal.
- 13-state order lifecycle with a transition table, `OrderEvent` history, and audit logging on every edge.
- "Verification is the approval" model — one routine human checkpoint, auto-release for standard orders, `REQUIRES_REVIEW` routing for flagged ones.
- Internal Birthday app: dashboard, live upcoming-birthday directory + manual detection trigger, order register + full per-order workflow UI, supplier management incl. locations, catalogue, and supplier-user administration.
- Supplier Portal: fulfilment-only dashboard, supplier-scoped order list + detail, merged accept, supplier-drivable status progression (from a single shared allow-list), problem reporting.
- Two supplier auth modes behind one `SUPPLIER_AUTH_MODE` switch, both minting the identical session token so authorization/isolation is mode-independent.
- Real Entra ID B2B guest sign-in implemented, deployed, and live in hosted DEV (`entra` mode active), with fail-closed application-level authorization against an ACTIVE `SupplierUser` and durable `entra_object_id` linking.
- Clean People integration boundary (consume `people-api` only; no BambooHR credential; no mirror table; static guard test).
- Mock email path with real `SupplierCommunication` records and failure handling.
- 203 automated tests green across the three apps.
- Deployed to hosted Azure DEV: 3 Container Apps + 1 scheduled scan job + 1 migrate job, DB at migration head, secrets in Key Vault.
- Documentation: `docs/platform/birthday-supplier-authentication.md`, `docs/birthday/requirements.md`, `docs/birthday/end-to-end-workflow.md`, `docs/birthday/current-workflow-review.html`.

---

## PART 19 — Known Gaps / Unfinished (classified)

**BLOCKER (must clear before any real DEV validation run)**
- **G1** `birthday-api` runs `INTEGRATIONS_MODE=mock` in hosted DEV — detection never sees live BambooHR staff. Flipping to `live` (Bicep param + redeploy `birthday-api` only) is the gate for a real detection run.
- **G2** The live external-supplier B2B sign-in has never been completed by a human, so the whole supplier half of the workflow is unverified end-to-end in hosted DEV.

**HIGH**
- **G3** "Test Supplier" has **no catalogue items and no locations** → every detected order would sit in `REQUIRES_ATTENTION / NO_DEFAULT_CAKE`; office-based supplier routing is untestable.
- **G4** `SupplierUser` id 1's `entra_object_id` is `NULL` and its email is a personal Gmail. First real sign-in will stamp the oid; until then the only join key is a case-insensitive email match.
- **G5** No `birthday-web` component/page tests and no browser-level E2E for either frontend.

**MEDIUM**
- **G6** Ops notifications for scan failure / detection deferral / exception build-up are lighter than the DijiOne source-sync contract's "operational warning to TA_MANAGER/admin"; deferral is recorded on `ScanRun` but not pushed.
- **G7** `platform-api`'s `ApplicationModule` registry row for `birthday` is not managed here; `birthday-api` unilaterally reports `product_status:"ACTIVE"`. The registry flip is a separate, unperformed step.
- **G8** Real Graph email (`GraphEmailClient`) is code-only; the independent Graph app-registration seam is unconfigured. (Deliberate — out of DEV scope — but a gap for UAT.)
- **G9** Inbound supplier email replies (`INBOUND`/`REPLIED`) are reserved constants with no ingestion path.

**LOW**
- **G10** Feb-29 handling resolves to Mar 1 in non-leap years — correct, but worth a product confirmation.
- **G11** `birthday-api /health/deep` `people_source: degraded` on a `people-api` cold start can look alarming in dashboards; it is by design (non-fatal).
- **G12** `employee_number` is nullable on `birthday_orders`; detection falls back to `employee_id` for the order reference — fine, but the two identifiers should be reconciled once live data is seen.

**DEFERRED (explicitly not in DEV scope)**
- Real birthday email sending · UAT/PROD provisioning · Teams channel · a generic external-user identity framework · separate External ID / CIAM tenant.

---

## PART 20 — Expansion Opportunities (do NOT implement)

**A — Required before UAT**
- A1 Configure the independent Graph app-registration + flip `EMAIL_SENDING_MODE` to real Graph email in UAT; verify a real supplier email is delivered.
- A2 Real DEV/UAT supplier records (not "Test Supplier"): at least one supplier with locations + a default catalogue item; a real supplier contact email.
- A3 Manage the `platform-api` `ApplicationModule` registry row for `birthday` as part of the deploy, not hardcoded.
- A4 Ops-notification wiring for scan failure / prolonged detection deferral / exception backlog, per the DijiOne source-sync contract.
- A5 Browser-level E2E covering both the internal workflow and the supplier portal (incl. isolation).

**B — Recommended before PROD**
- B1 Inbound supplier-reply ingestion (email → `SupplierCommunication` `INBOUND`/`REPLIED` → `OrderIssue`).
- B2 Supplier-side acknowledgement SLA enforcement (config has `acknowledgement_sla_hours`; nothing acts on it).
- B3 Address-verification workflow hardening — a real "request address confirmation from the employee/manager" loop rather than an ops-only manual check.
- B4 Retry/backoff + dead-letter visibility for failed supplier emails beyond `retry_count`.
- B5 Per-supplier user management UI polish (invite state, last-sign-in, oid link visibility).

**C — Nice-to-have**
- C1 Multi-cake / multi-recipient orders (team birthdays).
- C2 Supplier delivery-proof upload (photo) on `DELIVERED`.
- C3 Reporting model for birthday-fulfilment metrics feeding platform analytics.
- C4 Calendar/Teams reminder to the office contact on delivery day.
- C5 Configurable per-office cake budgets / catalogue restrictions.

---

## PART 21 — Product / UX Review

**Strengths**
- The "verification is the approval" model keeps the internal workload to one deliberate checkpoint per standard order — the right default for a low-stakes, high-volume workflow.
- The supplier portal is correctly scoped to *fulfilment only* — no recipient PII beyond first name + office until the address is verified, no internal notes, no other suppliers' data.
- One shared session-token mint for both auth modes means the isolation logic can't drift between "dev" and "real".
- Exception typing (`MISSING_EMAIL`, `NO_SUPPLIER`, `NO_DEFAULT_CAKE`, `SHORT_NOTICE_LEAD_TIME`, …) gives the ops user a precise worklist rather than a vague "needs attention".

**Friction / risks to watch when using it for real**
- With the current single skeleton supplier, the very first real detection run will dump **every** order into `REQUIRES_ATTENTION / NO_DEFAULT_CAKE` — a poor first impression that is really a data-setup gap (G3), not a bug.
- The internal order-detail page is large (~800 lines, 6 sections). Worth watching whether ops users can find the one action they need (Verify) without scrolling past assignment/address/requirements/comms/history.
- "Sign in with Microsoft" for an external supplier assumes the supplier contact has, or will accept, a Microsoft B2B guest invite. For a small local bakery this may be real friction; the fallback story (what if they won't/can't) is currently "they get no access".
- The supplier "Accept" is irreversible into `CONFIRMED` with only `PREPARING` / `UNABLE_TO_FULFIL` / `CANCELLED` forward — a supplier who accepts by mistake must use "Report a Problem". Acceptable, but a supplier "undo within N minutes" would reduce support load.
- `days_remaining >= supplier.lead_time_days` gating to `PENDING_VERIFICATION` vs `ON_HOLD` is invisible to the ops user until they open the order; a dashboard "N orders on hold for lead time" counter would help.
- Feb-29 birthdays silently become Mar-1 orders (G10) — fine, but a one-line note in the order history ("birthday falls on Feb 29; scheduled for Mar 1") would pre-empt questions.

**Copy / brand**: consistent with DijiOne ("DijiBirthday · by Dijital Team", warm design-system components, no rogue blue). The removal of "This environment is running in development mode" from the Entra login screen is correct and verified.

---

## PART 22 — Next Recommended DEV Iteration (do NOT execute)

**Philosophy:** DEV *construction* is complete. The next iteration is about **using DijiBirthday in DEV with real data**, finding the workflow / UX / data-shape gaps that only surface in a real run, fixing them in DEV, and *not* rushing to UAT/PROD.

Suggested sequence (each step is a DEV activity, reversible, no new Azure spend):

1. **Turn on live People data for Birthday.** Set `birthday-api` `INTEGRATIONS_MODE=live` (Bicep param, redeploy `birthday-api` only). Confirm `/health/deep` shows `integrations_mode: live` and `people_source: ok`.
2. **Set up one realistic DEV supplier.** Give "Test Supplier" (or a new one) at least one `supplier_locations` row matching a real office and 2–3 `supplier_catalogue_items` with one marked default. Add a real `SupplierUser` with a mailbox the team controls.
3. **Complete the pending human Entra sign-in** for the supplier and run the full verification checklist (auth → `SupplierUser` match → `entra_object_id` stamped → session → portal access → isolation → logout → persona endpoints 404). Record PASS/BLOCKED.
4. **Run a real detection scan** (`POST /api/birthday/admin/run-detection` or wait for `birthday-scan-job`). Review every resulting order: are the eligibility decisions right? Are exceptions correct? Is the office→supplier routing sane? Are addresses coming through from People?
5. **Drive 2–3 orders end to end by hand**: fix exceptions → verify address → (auto-release or confirm-release) → mock email → supplier accepts → preparing → out for delivery → delivered → auto-complete. Read the `OrderEvent` history and the audit trail; check they tell the true story.
6. **Deliberately break things**: take `people-api` cold during a scan (expect `DEFERRED_SOURCE_UNAVAILABLE`, zero orders, self-heal next run); deactivate the `SupplierUser` mid-session (expect next portal request 403); try to fetch another supplier's order id (expect 404).
7. **Log the gaps** found in steps 4–6 as DEV backlog items (UX, copy, missing counters, notification gaps, data reconciliation) and fix the cheap ones in DEV.
8. **Only then** write the UAT-readiness delta (Graph email, real suppliers, module-registry management, ops notifications, E2E tests — PART 20 group A).

---

# HANDOVER CONTEXT — DIJIBIRTHDAY

*Dense, self-contained summary for pasting into a fresh conversation. Everything below is current as of repo HEAD `96e3cc7` on branch `local/azure-dev-prep`, 2026-09-09.*

**What DijiBirthday is.** A DijiOne platform module that automates ordering birthday cakes for Dijital Team staff. Two frontends (`apps/birthday-web` internal, `apps/birthday-supplier-web` external) + one API (`apps/birthday-api`) + one database (`birthday_dev`, PostgreSQL). Part of a Domain-Driven Distributed Modular Platform: independently deployable domain services behind one gateway, each owning its own DB, hosted on Azure Container Apps.

**Core flow.** A daily Azure Container Apps Job (`birthday-scan-job`, cron `30 5 * * *`) calls `birthday-api`'s internal daily-scan endpoint. The detection engine reads active staff from `people-api` (the platform's sole BambooHR owner, read-only, live in DEV), and for each employee with a birthday inside the scan window (default −1…+14 days) idempotently creates one `BirthdayOrder` (`UniqueConstraint(employee_id, birthday_year)`), snapshotting the employee's name/email/address/office onto the order row. Each order gets an initial status: `REQUIRES_ATTENTION` (with a typed `exception_reason`) if it's missing an email, supplier, or default cake; else `PENDING_VERIFICATION` or `ON_HOLD` depending on supplier lead time. An internal ops user fixes exceptions and performs the one routine checkpoint — **"Verify address"** — which auto-releases standard orders to `SENT_TO_SUPPLIER` (triggering a supplier email) or routes flagged ones to `REQUIRES_REVIEW` for an explicit "Confirm release". The supplier then drives fulfilment through the portal: Accept → Preparing → Out for Delivery → Delivered; the system auto-completes `DELIVERED → COMPLETED`. Every transition is guarded by a transition table, writes an `OrderEvent`, and logs to `platform-api`'s audit service.

**Architectural rules that MUST NOT be reversed.**
1. `birthday-api` never queries `people_dev` directly and never calls BambooHR directly — only `people-api` via `EmployeeDirectoryClient`. Enforced by `tests/test_no_direct_bamboohr_dependency.py`.
2. `birthday-api` holds **no employee mirror/projection table**. A `people-api` outage → scan defers (`ScanRun.status = DEFERRED_SOURCE_UNAVAILABLE`), zero orders touched, self-heals next run. In-flight orders are safe because employee facts are snapshotted onto the order at detection time.
3. **Entra authenticates; an ACTIVE `SupplierUser` row authorizes.** Entra B2B guest membership alone grants zero Birthday access. `SupplierUser` is **never** auto-created from a sign-in. Fail closed → generic 403.
4. `supplier_id` always comes from the server-side `SupplierUser` row, never from a request parameter/URL/body. Re-checked every request in `get_supplier_scope`.
5. Birthday email is behind a factory seam and is **mock** in DEV (`EMAIL_SENDING_MODE=mock`), independent of `INTEGRATIONS_MODE`. Do not enable real Birthday email without explicit scope.
6. `SUPPLIER_AUTH_MODE` (`dev`|`entra`) — not `APP_ENV` — is the authoritative control for the supplier auth experience and gates the dev persona endpoints (404 in `entra` mode).
7. Both supplier auth modes end at the same `mint_supplier_session_token`, so isolation logic is mode-independent — keep it that way.

**Auth specifics.** DijiOne session token = HS256, `iss = dijione-dev-identity`, signed with `JWT_DEV_SECRET`, carries `module_roles` ({role, permissions[]}) + optional `supplier` sub-claim; decoded locally by every service via `packages/auth-client-py`. Internal hosted DEV uses real Microsoft Entra (`AUTH_MODE=entra`) for staff. Supplier hosted DEV uses real Entra **B2B guest** in the existing Dijital Team tenant (tenant `2abce006-6ea2-4675-b39d-33e0a54c46c7`), app registration `dijione-birthday-supplier-dev` (appId `30e36193-f0e4-40d5-875b-db1ef6a3f2b0`), single-tenant, Auth Code + PKCE, delegated `openid profile email`, redirect `https://birthday-supplier-web.livelypebble-890e141a.southeastasia.azurecontainerapps.io/api/auth/callback`, client secret in `kv-dijione-dev/birthday-supplier-entra-secret-dev`. `id_token` verified RS256/JWKS (iss/aud/tid/nonce/exp). B2B guest UPNs are rewritten to `<email>_<domain>#EXT#@…onmicrosoft.com` and must **never** be treated as an email — match on the verified `email` claim or the durable `oid`, which is stamped onto `SupplierUser.entra_object_id` on first sign-in.

**Order statuses (14):** `PENDING_VERIFICATION, REQUIRES_REVIEW, REQUIRES_ATTENTION, ON_HOLD, SENT_TO_SUPPLIER, CHANGE_REQUESTED, CONFIRMED, PREPARING, OUT_FOR_DELIVERY, DELIVERED, COMPLETED, UNABLE_TO_FULFIL, CANCELLED`. Supplier-drivable edges only: `SENT_TO_SUPPLIER→{CONFIRMED,CHANGE_REQUESTED,UNABLE_TO_FULFIL}`, `CONFIRMED→PREPARING`, `PREPARING→OUT_FOR_DELIVERY`, `OUT_FOR_DELIVERY→DELIVERED`.

**Data model:** 12 tables — `birthday_orders` (~40 cols, the aggregate), `suppliers`, `supplier_users` (`entra_object_id` nullable unique), `supplier_catalogue_items`, `supplier_locations`, `supplier_communications`, `order_events`, `order_issues`, `special_requirements`, `scan_runs`, `order_sequences`, `birthday_detection_configs`. 11 Alembic migrations, head `c4f6a8b0d2e4_drop_phase3_mock_orders`; DB confirmed at head.

**Hosted Azure DEV (RG `rg-dijione-dev`, subscription "Dijital Team IT Production", SE Asia):** 3 Container Apps (`birthday-api` internal `@sha256:aed4bf05…`, `birthday-web` internal `@sha256:b555b230…`, `birthday-supplier-web` **external** `@sha256:78aac896…`), all min 0 / max 1, 0.25 vCPU / 0.5 GiB. `birthday-scan-job` cron `30 5 * * *`. `birthday-api` env: `APP_ENV=development, INTEGRATIONS_MODE=mock, EMAIL_SENDING_MODE=mock, SUPPLIER_AUTH_MODE=entra`. KV secrets: `database-url-birthday`, `birthday-supplier-entra-secret-dev`. Live: `/api/birthday/supplier/auth/config` → `{"supplier_auth_mode":"entra"}`, `/login-url` → 200.

**Live data (`birthday_dev`):** 0 birthday orders, 1 supplier ("Test Supplier", ACTIVE, lead 7d, **no locations, no catalogue items**), 1 `SupplierUser` (id 1, `madusankaweeriyasinghe20@gmail.com`, "Kumar Sangakkara", ACTIVE, SUPPLIER_ADMIN, `entra_object_id = NULL`). `people_dev`: ~337 live BambooHR employees, no mock rows.

**Tests:** `birthday-api` 195 pass (`pytest`), `birthday-supplier-web` 6 pass, `birthday-web` 2 pass (`vitest`). No browser E2E; `birthday-web` has no per-page tests; Entra JWKS + code exchange are mocked in `birthday-api` tests.

**Current status: FUNCTIONALLY COMPLETE BUT NEEDS BUSINESS VALIDATION.** All code + tests done and deployed. NOT done: (a) any real business run against live BambooHR data — `birthday-api` is still `INTEGRATIONS_MODE=mock`; (b) the interactive human Microsoft Entra B2B supplier sign-in and its post-sign-in verification checklist (all autonomous prep is done: guest Accepted, oid `5847f827-d893-46fc-af54-0214a1619c21`, admin consent granted, secret + app reg + redirect in place); (c) a realistic DEV supplier with locations + catalogue. Open business decision unrelated to Birthday scope but tracked in `docs/platform/DEV-BUSINESS-PROCESS-GAPS.md`: the "National Tech" DTC tag in TalentFlow.

**Do NOT, without explicit scope:** enable real Birthday/Graph email; provision UAT/PROD; create a separate External ID/CIAM tenant; auto-create `SupplierUser`s; let `birthday-api` reach BambooHR or `people_dev` directly; perform GitHub remote operations (push/PR/branch) — the remote freeze is in force; local commits are fine.

**Recommended next iteration:** flip `birthday-api` to `INTEGRATIONS_MODE=live`, set up one realistic DEV supplier (locations + default cake), complete the human Entra sign-in + verification, run a real detection scan, drive 2–3 orders end-to-end by hand, deliberately break `people-api`/`SupplierUser`/isolation to confirm the fail-safes, log the gaps, fix the cheap ones in DEV — *then* write the UAT-readiness delta. Do not rush to UAT/PROD.
