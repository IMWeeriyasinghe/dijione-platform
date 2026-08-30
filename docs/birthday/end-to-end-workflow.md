# DijiBirthday — End-to-End Workflow, Architecture & Operations

Status: current as of 2026-08-29 (QA/QC hardening pass).

This document is the single reference for how **DijiBirthday** (internal) and
the **DijiBirthday Supplier Portal** (external B2B) work together, how they
are authorized, and what remains a deployment/configuration task.

---

## A. Architecture

DijiBirthday is a DijiOne module built as independently deployable services,
consistent with `docs/platform/service-architecture.md`:

| Component | Tech | Port (dev) | Audience | Talks to |
|---|---|---|---|---|
| `apps/birthday-web` | Next.js 16 | 3003 | Internal staff (via shell-web zone) | `birthday-api` |
| `apps/birthday-supplier-web` | Next.js 16 | 3006 | External supplier users | `birthday-api` (`/api/birthday/portal/*` only) |
| `apps/birthday-api` | FastAPI | 8003 | both frontends + schedulers | SQLite (dev) / PostgreSQL (prod), BambooHR (read-only), Microsoft Graph (email, mocked) |
| `apps/platform-api` | FastAPI | 8000 | all modules | issues JWT claims, stores audit log + notifications |

Principles preserved:

- **No direct frontend → BambooHR access.** Only `birthday-api` calls BambooHR,
  read-only, behind `app/integrations/bamboohr/`.
- **No supplier frontend → internal frontend dependency.** `birthday-supplier-web`
  is a standalone app with its own shell, its own auth context, and an API
  client (`src/lib/api.ts`) that can only reach `/api/birthday/portal/*`.
- **Service-owned business logic.** Eligibility, detection, readiness, status
  transitions, address verification and the supplier DTO are all computed in
  `birthday-api` services and never re-derived in a frontend.
- **Database-enforced safeguards.** Idempotency (`uq_birthday_orders_employee_year`),
  order-reference uniqueness, `supplier_users.entra_object_id` uniqueness.

---

## B. Internal DijiBirthday workflow

Pages (`apps/birthday-web/src/app`):

| Route | Purpose | Sidebar active |
|---|---|---|
| `/birthday` | Dashboard (counts, exceptions, upcoming) | Dashboard only |
| `/birthday/upcoming` | Upcoming Birthdays — live BambooHR directory, eligibility, address & order status, Order Reference | Upcoming Birthdays only |
| `/birthday/orders` | Cake Orders register (search / filter / sort / paginate) | Cake Orders only |
| `/birthday/orders/{id}` | Order detail — timeline, address verification, supplier/product assignment, hold/release/cancel, submit-for-approval, approve/reject, send-to-supplier | Cake Orders only |
| `/birthday/suppliers` | Suppliers register (row is a link to detail) | Suppliers only |
| `/birthday/suppliers/{id}` | Supplier detail — profile, locations, catalogue, **Supplier Users** (incl. Entra Object ID link) | Suppliers only |

The DijiBirthday / "by Dijital Team" brand in the shell header routes back to
DijiOne Home (`homeHref="/"`, a plain cross-zone `<a>`).

Terminology: the UI says **Team Member** for employee and **Team Member ID**
for BambooHR `employeeNumber`. Backend/database identifiers
(`employee_id`, `employee_number`) are deliberately unchanged.

---

## C. Supplier Portal workflow

`apps/birthday-supplier-web` — external, deliberately not styled or
structured like an internal DijiOne module (no DijiOne sidebar, no internal
nav). Screens: login (Entra B2B in prod / dev persona picker locally),
dashboard + order list, order detail with fulfilment actions, raise-issue,
sign out. Loading / error / empty states on every data view. The order
detail now shows the **verified delivery address** (only when
`address_verified` is true).

---

## D. Interaction between the two applications

```
BambooHR (read-only)
   │  list_active_employees()
   ▼
birthday-api  ──detection──►  BirthdayOrder (DRAFT, order_reference, address snapshot)
   │                                   │
   │  internal staff (birthday-web)    │  approve()  → approved_at / approved_by stamped
   ▼                                   ▼
address verified ─► READY_FOR_APPROVAL ─► APPROVED ─► send-to-supplier (email MOCKED)
                                                          │  status = SENT_TO_SUPPLIER
                                                          ▼
                                       birthday-api  /api/birthday/portal/*  (supplier-scoped)
                                                          ▲
                                       birthday-supplier-web  (Entra B2B guest token)
```

The two apps never call each other directly — they share only `birthday-api`
and its database, through disjoint route groups (`/orders`, `/suppliers` vs
`/portal`).

---

## E. Microsoft Entra ID B2B authentication (production supplier auth)

The Supplier Portal authenticates **external supplier guest identities** via
**Microsoft Entra ID B2B guest access**. There are no local supplier
passwords, no username/password store, and no magic links.

Production flow:

```
External supplier user
  → Microsoft Entra ID B2B guest sign-in (OIDC Authorization Code + PKCE)
  → birthday-supplier-web receives an ID/access token
  → token sent as Bearer to birthday-api
  → birthday-api validates: signature (tenant JWKS), issuer, audience, expiry
  → the token's object-id claim (`oid`) is read
  → SupplierUser row looked up by entra_object_id
  → SupplierUser.status == ACTIVE  AND  Supplier.status == ACTIVE
  → supplier_id resolved SERVER-SIDE (from the row, never the request)
  → every query constrained to that supplier_id
```

**Token-validation decision:** the durable identity key is the Entra
**object id** (`oid`) claim, not `email` (email can change; `oid` does not).
`birthday-api` must validate the token against the configured tenant's JWKS
and check `iss` / `aud` / `exp` — not merely decode it. The current
`auth_client_py` seam decodes an HS256 dev JWT; wiring RS256 + JWKS + issuer
/ audience validation for the B2B tenant is the **deployment task** in §Q.

Local development uses `app/api/routes/dev_auth.py`
(`/api/birthday/internal/dev/supplier-*`), which:

- is **hard-disabled when `APP_ENV=production`** (returns 404, not 403 — the
  route is not even discoverable);
- lets a caller pick *which seeded `SupplierUser` to become*, never a
  `supplier_id`;
- resolves `supplier` claim → `SupplierUser` → `supplier_id` through the
  **exact same** `SupplierScope` path production uses.

---

## F. SupplierUser authorization mapping

`supplier_users` (`app/models/supplier_user.py`):

| Field | Notes |
|---|---|
| `id` | PK |
| `supplier_id` | FK → `suppliers.id`, the isolation boundary |
| `full_name`, `email` | contact info; `email` is unique but **not** the identity key |
| `role` | `SUPPLIER_USER` \| `SUPPLIER_ADMIN` (carried; both get the same portal claims today) |
| `status` | `ACTIVE` \| `INACTIVE` — re-checked on **every** request in `get_supplier_scope` |
| `entra_object_id` | Microsoft Entra B2B guest `oid`; nullable until linked; **unique**; authoritative once set |
| `created_at`, `updated_at` | timestamps |

Internal admin management: `POST/GET/PATCH /api/birthday/suppliers/{id}/users`.
`PATCH` covers email/name/role, activate/deactivate, **and linking /
updating `entra_object_id`** (added in the QA/QC pass — uniqueness enforced,
`""` normalised to `NULL`, audited as `birthday.supplier.user_entra_linked`).
SupplierUsers are never hard-deleted (deactivate only), so historical
`OrderEvent.actor_id` references stay resolvable.

---

## G. Supplier isolation (critical)

Enforced entirely server-side in `birthday-api`:

- `SupplierScope.supplier_id` comes **only** from the validated token claim →
  DB row; never from a URL/query/body parameter.
- Every `/portal/*` repository call filters on `scope.supplier_id`
  (`BirthdayOrderRepository.list_for_supplier` / `count_for_supplier` /
  `get_for_supplier`).
- A manipulated order id belonging to another supplier returns **404**, not
  403 — the caller learns nothing.
- `get_for_supplier` also excludes orders not yet in a supplier-visible
  status, so a DRAFT/READY/APPROVED order is invisible to the supplier until
  it is actually sent.
- Inactive `SupplierUser` → 403; inactive `Supplier` → the user's orders are
  still row-scoped and the dev login refuses inactive personas.
- `SupplierOrderView` is a **separate** Pydantic model — HR fields (hire
  date, termination date, employment status, eligibility reason, internal
  notes, `employee_id`, `employee_number`) are never selected into it.

Regression coverage: `tests/test_supplier_portal.py`,
`tests/test_supplier_admin.py::test_cross_supplier_isolation_*`.

---

## H. User persona matrix

| Role | App | View | Create | Edit | Approve | Supplier actions | User admin |
|---|---|---|---|---|---|---|---|
| **INTERNAL ADMIN** (`BIRTHDAY_ADMIN`) | birthday-web | ✅ all | ✅ orders, suppliers, supplier-users | ✅ orders, suppliers | ✅ approve/reject | — | ✅ SupplierUser CRUD + Entra link |
| **INTERNAL OPS / CS / P&C** (`BIRTHDAY_USER` + granted perms) | birthday-web | ✅ dashboard, orders, suppliers | ➖ (perm-gated) | ✅ address verification, supplier/product assignment | ➖ | — | ➖ |
| **INTERNAL APPROVER** (`birthday.orders.approve`) | birthday-web | ✅ orders | ➖ | ➖ | ✅ approve/reject/hold | — | ➖ |
| **SUPPLIER ADMIN** (`SUPPLIER_ADMIN`) | supplier-web | ✅ own supplier orders | — | — | — | ✅ acknowledge → delivered, issue/change | — |
| **SUPPLIER USER** (`SUPPLIER_USER`) | supplier-web | ✅ own supplier orders | — | — | — | ✅ acknowledge → delivered, issue/change | — |

Permission keys are carried on the JWT `module_roles.birthday.permissions`
claim (see `tests/conftest.py::BIRTHDAY_PERMISSIONS_BY_ROLE` for the dev set).
`SUPPLIER_ADMIN` vs `SUPPLIER_USER` currently receive identical portal
claims (`birthday.portal.access`, `birthday.portal.respond`); the role is
stored for future finer-grained gating.

---

## I. Birthday detection

`app/services/detection_service.py::run_daily_scan`:

1. `bamboohr_client.list_active_employees()` (status=Active only).
2. For each: compute next birthday occurrence (year-boundary safe; Feb 29 →
   Mar 1 in non-leap years).
3. Skip if outside the configured scan window
   (`window_lookback_days … window_lookahead_days`).
4. **Eligibility gate** (see §J) — ineligible employees never get a row.
5. Resolve supplier by office location (ACTIVE suppliers only).
6. Generate `order_reference` (`BDAY-EMP{employee_id}-{year}-{NNNNN}` from the
   `order_sequences` counter table, retry-safe).
7. `create_or_get_order` — insert inside a SAVEPOINT; on the
   `(employee_id, birthday_year)` unique-constraint violation, return the
   existing row untouched (**idempotent**, quantity never incremented).
8. Copy the BambooHR address into the order snapshot,
   `delivery_address_source = BAMBOOHR`, `address_verification_status =
   NOT_CHECKED`.
9. Commit per employee (one bad record cannot abort the run).

Result summary: `employees_scanned`, `orders_created`, `orders_existing`,
`exceptions`, `ineligible_skipped`, `errors[]`.

---

## J. Eligibility state machine

`app/services/eligibility_service.py::compute_eligibility` — first failing
check wins:

1. valid birthday present → else `MISSING_BIRTHDAY`
2. month/day in range → else `INVALID_EMPLOYEE_DATA`
3. `employment_status == "Active"` → else `INACTIVE_EMPLOYEE`
4. hire date known → else `MISSING_HIRE_DATE`
5. hire date ≤ this birthday occurrence → else `FUTURE_STARTER`
6. no termination date before this occurrence → else `EMPLOYMENT_ENDED`
7. otherwise → `ELIGIBLE`

Future starters never receive an order before their start date.

---

## K. Order state machine

Statuses: `DRAFT → READY_FOR_APPROVAL → APPROVED → SENT_TO_SUPPLIER →
SUPPLIER_REVIEW → CONFIRMED → PREPARING → OUT_FOR_DELIVERY → DELIVERED →
COMPLETED`.

Exception / side paths: `ON_HOLD`, `CANCELLED`, `REJECTED`,
`CHANGE_REQUESTED`, `UNABLE_TO_FULFIL`, `REQUIRES_ATTENTION`.
`PLANNED` is a retained legacy status.

Transitions are enforced by the table in
`app/services/order_status_service.py::ALLOWED_TRANSITIONS`. No route mutates
`status` directly; every transition writes an `OrderEvent` **and** an audit
log entry.

**Approval provenance (QA/QC pass):** `approve()` now stamps `approved_at` /
`approved_by` on the order. `order_email_service._send()` gates on
`approved_at is not None` — closing the gap where a detection-time
`REQUIRES_ATTENTION` order (never approved) could be sent to a supplier just
because `REQUIRES_ATTENTION` was on the "retry a previously-approved send"
allow-list.

---

## L. Readiness (gate into READY_FOR_APPROVAL)

`app/services/readiness_service.py::check` — an order is ready only when:

- `address_verification_status == VERIFIED`
- `supplier_id` assigned
- `delivery_date` set  *(added in the QA/QC pass — §17)*
- `office_location` present
- `quantity >= 1`
- `employee_name` present

Product / catalogue selection (`catalogue_item_id`) is captured but not a
hard gate (a supplier can be assigned a default cake); it is surfaced in the
UI. Eligibility is not re-checked here — an ineligible employee never had a
row.

`submit_for_approval` and `approve` both re-run this check server-side.

---

## M. Address-verification state machine

`app/services/address_verification_service.py` — P&C-manual, **no automated
employee contact ever**, and no transition table (a P&C user may move
between any two states):

```
NOT_CHECKED ─► VERIFICATION_REQUESTED ─► VERIFIED
                                    └──► NEEDS_UPDATE ─► (edit address) ─► VERIFIED
```

Editing the address sets `delivery_address_source = MANUAL_CORRECTION`.
The audit trail records **only which field names changed**, never address
content (the order row is the source of the address; the audit log is not).
The supplier sees address fields **only** when `VERIFIED`.

---

## N. Approval

`DRAFT → READY_FOR_APPROVAL → APPROVED`; exits `REJECTED` / `ON_HOLD` /
`CANCELLED`. Approval captures `approved_by`, `approved_at`, an `OrderEvent`,
and an audit entry. A supplier cannot see an order before it is `APPROVED`
**and** sent (`SENT_TO_SUPPLIER`+).

---

## O. Supplier fulfilment state machine (portal actions)

`app/api/routes/portal.py::_SUPPLIER_ALLOWED_TARGETS`:

```
SENT_TO_SUPPLIER ──acknowledge──► SUPPLIER_REVIEW
SUPPLIER_REVIEW  ──► CONFIRMED | CHANGE_REQUESTED | UNABLE_TO_FULFIL
CONFIRMED        ──► PREPARING
PREPARING        ──► OUT_FOR_DELIVERY
OUT_FOR_DELIVERY ──► DELIVERED
```

Every portal action re-validates: authenticated `SupplierUser`, user ACTIVE,
supplier ACTIVE, supplier owns the order, current state, transition
validity. Each records actor + time + `OrderEvent` + audit entry.

---

## P. Issue / change workflow

Supplier raises an issue (`POST /portal/orders/{id}/issue`) — allowed only
while the order is **in progress** (`SENT_TO_SUPPLIER`, `SUPPLIER_REVIEW`,
`CHANGE_REQUESTED`, `CONFIRMED`, `PREPARING`, `OUT_FOR_DELIVERY`); blocked
(409) once terminal *(guard added in the QA/QC pass)*. The issue is recorded
as a `SUPPLIER_ISSUE` `OrderEvent`, audited, and broadcast to
`BIRTHDAY_ADMIN`. Internal ops then amend / hold / reassign / cancel /
re-release; audit history is preserved throughout.

---

## Q. External production scheduler requirement

Do **not** add an in-process scheduler to FastAPI. Production automatic
detection is:

```
Azure scheduled job (Function Timer / Logic App recurrence)
  → POST /api/birthday/internal/run-daily-scan  (X-Internal-Token: <INTERNAL_SERVICE_SECRET>)
  → run_daily_scan  (same service the manual/UAT path calls)
```

For UAT/ops, `POST /api/birthday/admin/run-detection`
(`birthday.config.manage` permission) calls the identical service — no
duplicated logic. The birthday-web "Run Birthday Detection" button (admin
only, Upcoming Birthdays page) is the front door for this.

Starting `npm run dev:all` does **not** run any scan or create any orders.

---

## R. Local development startup

```
npm run dev:all
```

starts every DijiOne service **including** `birthday-supplier-web` (port
3006, added in the QA/QC pass). It can also be started alone:

```
cd apps/birthday-supplier-web && npm run dev
```

Ports: shell-web 3000, birthday-web 3003, **birthday-supplier-web 3006**,
platform-api 8000, birthday-api 8003.

Environment (`apps/birthday-api/.env`): keep `INTEGRATIONS_MODE=live`
(BambooHR read-only) and `EMAIL_SENDING_MODE=mock`. `APP_ENV` must be
`production` in production so the dev supplier-auth routes 404.

---

## S. Deployment requirements

See §V of the QA/QC report. Summary: Entra B2B app registrations (portal SPA
+ API), API audience/scope, RS256 + JWKS + issuer/audience validation in
`birthday-api`, production redirect URIs, per-supplier `entra_object_id`
mapping, HTTPS, tightened CORS, production secrets, PostgreSQL + `alembic
upgrade head`, the external scheduler job, Application Insights, and — only
when explicitly approved — flipping `EMAIL_SENDING_MODE=live`.

---

## T. Database ownership

`birthday-api` owns: `birthday_orders`, `order_events`, `order_sequences`,
`special_requirements`, `birthday_detection_configs`, `suppliers`,
`supplier_locations`, `supplier_catalogue_items`, `supplier_users`,
`supplier_communications`. Users, audit log and notifications are owned by
`platform-api` (no FK from birthday tables into it — `actor_id` /
`created_by` are opaque ints).

Single Alembic head: `e7f2a0b1c9d3`.

---

## U. Known limitations

| Item | Class |
|---|---|
| Real Entra B2B tenant guest invitation flow + RS256/JWKS token validation | Deployment task |
| Scan-run history table (`GET /internal/scan-runs/{id}` returns 501) | Future enhancement |
| `SUPPLIER_ADMIN` vs `SUPPLIER_USER` finer-grained portal gating | Future enhancement |
| Module-`/summary` endpoints unauthenticated (platform-wide convention; 3 integer counts only) | Accepted / documented |
| Correcting a `VERIFIED` address does not auto-reset verification status (by design — caller re-verifies) | Accepted / documented |
| BambooHR fetched live per request (no local cache) | Future enhancement — see `docs/platform/performance-investigation.md` |
