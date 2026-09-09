# DijiBirthday — End-to-End Workflow, Architecture & Operations

Single reference for how **DijiBirthday** (internal) and the **DijiBirthday Supplier
Portal** (external Entra B2B) work together, how they are authorized, and what remains a
deployment task. Reflects the **shipped semi-automation model** — there is no
`DRAFT`/`READY_FOR_APPROVAL`/`APPROVED` workflow and no universal approval step.

---

## A. Architecture

| Component | Tech | Audience | Talks to |
|---|---|---|---|
| `apps/birthday-web` | Next.js | Internal staff (via `shell-web` `/birthday` zone) | `birthday-api` |
| `apps/birthday-supplier-web` | Next.js | External supplier users | `birthday-api` (`/api/birthday/portal/*` + `/api/birthday/supplier/auth/*`) |
| `apps/birthday-api` | FastAPI | both frontends + schedulers | `birthday_dev` (SQLite dev / PostgreSQL prod), `people-api` (employees, read-only), `platform-api` (JWT / audit / notifications), Microsoft Graph (email + inbound mail — **mock in DEV**) |
| `apps/platform-api` | FastAPI | all modules | issues session tokens, stores audit log + notifications |

Principles:

- **No direct frontend → BambooHR / People DB access.** Only `birthday-api` reaches People,
  and only via `auth_client_py.EmployeeDirectoryClient` → `people-api` (read-only). Adapter:
  `app/integrations/people_source/`. Static guard: `tests/test_no_direct_bamboohr_dependency.py`.
- **No supplier frontend → internal frontend dependency.** `birthday-supplier-web` is
  standalone with its own shell, auth context, and an API client that can only reach
  `/api/birthday/portal/*` and `/api/birthday/supplier/auth/*`.
- **Service-owned business logic.** Eligibility, detection, readiness, status transitions,
  address verification, the supplier DTO, and communication correlation are computed in
  `birthday-api` and never re-derived in a frontend.
- **DB-enforced safeguards.** `UniqueConstraint(employee_id, birthday_year)`,
  `order_reference` uniqueness, `supplier_users.entra_object_id` uniqueness.

---

## B. Internal DijiBirthday workflow (`apps/birthday-web/src/app`)

| Route | Purpose |
|---|---|
| `/birthday` | Dashboard — actionable attention cards (verification required/overdue, in review, exceptions, supplier not accepted, deliveries at risk, on-hold, detection health) each deep-linking to a filtered order list |
| `/birthday/upcoming` | Upcoming Birthdays — the forward-looking **people** view: who has a birthday coming up, eligibility, whether an order exists and its state; "Run detection" |
| `/birthday/orders` | Cake Orders register — the order **lifecycle** worklist (saved views, search, filter, sort, paginate) |
| `/birthday/orders/{id}` | Order detail — header + primary action, address verification, fulfilment assignment, **Unified Timeline** (comms + events + issues), advanced/raw log |
| `/birthday/suppliers` | Suppliers register |
| `/birthday/suppliers/{id}` | Supplier detail — profile, locations, catalogue (default cake), **Supplier Users** (Entra link + onboarding state), setup-readiness panel, internal notes |

UI terminology: **Team Member** for employee, **Team Member ID** for BambooHR
`employeeNumber`. DB identifiers (`employee_id`, `employee_number`) are unchanged.

---

## C. Supplier Portal workflow (`apps/birthday-supplier-web`)

External, deliberately not styled like an internal DijiOne module. Screens: sign-in (Entra
B2B in hosted DEV / persona picker only when `SUPPLIER_AUTH_MODE=dev`), fulfilment-only
dashboard, order list (default-sorted by delivery date, overdue flagged), order detail with
fulfilment actions + the supplier-filtered Unified Timeline + a Portal reply box, sign out.
Loading / error / empty states on every data view. The delivery address is shown only once
`address_verified` is true.

---

## D. Interaction between the two applications

```
BambooHR (read-only) ──people-api──► birthday-api
   │  list_active_employees()
   ▼
detection ─► BirthdayOrder (PENDING_VERIFICATION | REQUIRES_ATTENTION | ON_HOLD,
             order_reference, supplier + default cake auto-assigned,
             delivery_date defaulted, address + employee facts snapshotted, verify_by)
   │
   │  internal staff (birthday-web): fix exceptions, then the ONE routine action —
   │  "Verify address"  (POST /orders/{id}/verify)
   ▼
   standard order      → auto-release → SENT_TO_SUPPLIER  (outbound email, mock in DEV)
   flagged order       → REQUIRES_REVIEW → one-click "Confirm & release" → SENT_TO_SUPPLIER
   not ready           → REQUIRES_ATTENTION (typed)
   ▼
supplier (birthday-supplier-web, Entra B2B):
   Accept → CONFIRMED → PREPARING → OUT_FOR_DELIVERY → DELIVERED
   ▼
system: DELIVERED → COMPLETED  (auto, no internal button)

Communication (either direction, either channel) is recorded as SupplierCommunication and
rendered in the order's Unified Timeline on both sides.
```

---

## E. Microsoft Entra ID B2B authentication (production supplier auth)

The Supplier Portal authenticates external supplier identities via **Microsoft Entra ID B2B
guest access** — no local passwords, no magic links. `SUPPLIER_AUTH_MODE` (`dev` | `entra`)
is the authoritative switch (**not** `APP_ENV`); hosted DEV runs `entra`.

```
external supplier user
  → Entra B2B guest sign-in (OIDC Authorization Code + PKCE), separate app registration
  → birthday-supplier-web server-side code exchange → id_token
  → birthday-api core/supplier_entra.py: RS256/JWKS verify (iss, aud, tid, nonce, exp)
  → resolve_supplier_user(): match entra_object_id (oid); else verified email
    (a rewritten #EXT# UPN is NEVER treated as an email); stamp oid on first email match
  → SupplierUser.status == ACTIVE  AND  Supplier.status == ACTIVE  (else generic 403)
  → mint_supplier_session_token(): DijiOne HS256 session token, supplier claim + supplier_id
  → every /portal/* query constrained to that supplier_id, re-checked each request
```

**Entra authenticates; an ACTIVE `SupplierUser` authorizes.** Entra membership alone grants
nothing. A `SupplierUser` is **never** auto-created from a sign-in. Config reference:
`docs/platform/birthday-supplier-authentication.md`. When `SUPPLIER_AUTH_MODE=dev`,
`app/api/routes/dev_auth.py` (`/api/birthday/internal/dev/supplier-*`) offers a seeded-persona
picker resolving through the **same** `SupplierScope` path; those routes **404** under
`entra`.

---

## F. SupplierUser authorization mapping

`supplier_users` (`app/models/supplier_user.py`):

| Field | Notes |
|---|---|
| `supplier_id` | FK → `suppliers.id`, the isolation boundary |
| `email` | contact + email-match key on first sign-in; unique; not the durable identity key |
| `role` | `SUPPLIER_USER` \| `SUPPLIER_ADMIN` (carried; both get the same portal claims today) |
| `status` | `ACTIVE` \| `INACTIVE` — re-checked on **every** request in `get_supplier_scope` |
| `entra_object_id` | Entra B2B guest `oid`; nullable until linked; unique; authoritative once set |
| `invited_at` / `linked_at` / `last_login_at` | onboarding-state visibility for internal admins |

Internal admin management: `GET/POST/PATCH /api/birthday/suppliers/{id}/users`. `PATCH`
covers email/name/role, activate/deactivate, and `entra_object_id` linking (uniqueness
enforced, `""`→`NULL`, audited `birthday.supplier.user_entra_linked`). Never hard-deleted.

---

## G. Supplier isolation (critical)

Server-side in `birthday-api`: `SupplierScope.supplier_id` comes only from the validated
token → DB row, never a URL/query/body parameter; every `/portal/*` repository call filters
on it; a manipulated order id belonging to another supplier **404s** (the caller learns
nothing). `SupplierOrderView` is a separate Pydantic model — HR fields are never selected
into it. Terminal statuses stay portal-visible so a cancellation shows as a tombstone.

---

## H. Birthday detection (`app/services/detection_service.py`)

`run_daily_scan` opens a `ScanRun`, fetches active employees via `people-api`, and per
in-window employee:

- next occurrence (Feb 29 → Mar 1 off-leap); scan window `-lookback … +lookahead` days;
- eligibility ladder (`eligibility_service`): `MISSING_BIRTHDAY` → `INVALID_EMPLOYEE_DATA`
  → `INACTIVE_EMPLOYEE` → `MISSING_HIRE_DATE` → `FUTURE_STARTER` → `EMPLOYMENT_ENDED` →
  `ELIGIBLE` (future starters don't count as exceptions);
- lead-time class Normal / Short-Notice / Urgent vs `supplier.lead_time_days`;
- deterministic supplier resolution: sole ACTIVE → office-location rule → `is_default` → none;
- default cake: single default → single item → none → `NO_DEFAULT_CAKE`;
- `verify_by = occurrence − (lead_time_days + verify_buffer_days)`;
- **address + employee facts snapshotted onto the order** (never a live lookup later);
- `create_or_get_order` — idempotent on `(employee_id, birthday_year)`, per-employee commit.

**Source outage:** `EmployeeSourceUnavailableError` → `ScanRun.status =
DEFERRED_SOURCE_UNAVAILABLE`, zero orders, nothing touched; the next scan recomputes each
employee's next occurrence and catches up within the lookahead window — no duplicates.

Production detection = the external `birthday-scan-job` (`30 5 * * *`) hitting
`POST /api/birthday/internal/run-daily-scan` (X-Internal-Token). `POST
/api/birthday/admin/run-detection` is the auth-gated UAT/ops equivalent, same service.

---

## I. Order state machine (`app/services/order_status_service.py`)

**13 active statuses.** `ALLOWED_TRANSITIONS` is the single source of truth; every
transition goes through `transition(...)`, writes an `OrderEvent`, and best-effort
`AuditService.log("birthday.order.status_change")`. No route mutates `status` directly.

```
PENDING_VERIFICATION → REQUIRES_REVIEW | SENT_TO_SUPPLIER | ON_HOLD | REQUIRES_ATTENTION | CANCELLED
REQUIRES_REVIEW      → SENT_TO_SUPPLIER | ON_HOLD | REQUIRES_ATTENTION | CANCELLED
REQUIRES_ATTENTION   → PENDING_VERIFICATION | SENT_TO_SUPPLIER | ON_HOLD | CANCELLED | REQUIRES_ATTENTION
ON_HOLD              → PENDING_VERIFICATION | REQUIRES_REVIEW | SENT_TO_SUPPLIER | CANCELLED
SENT_TO_SUPPLIER     → CONFIRMED | CHANGE_REQUESTED | UNABLE_TO_FULFIL | ON_HOLD | REQUIRES_ATTENTION | CANCELLED
CHANGE_REQUESTED     → SENT_TO_SUPPLIER | CANCELLED
CONFIRMED            → PREPARING | UNABLE_TO_FULFIL | CANCELLED
PREPARING            → OUT_FOR_DELIVERY | UNABLE_TO_FULFIL | CANCELLED
OUT_FOR_DELIVERY     → DELIVERED | REQUIRES_ATTENTION | CANCELLED
DELIVERED            → COMPLETED            UNABLE_TO_FULFIL → REQUIRES_ATTENTION
CANCELLED / COMPLETED → (terminal)
```

`SUPPLIER_DRIVABLE` (portal only): `SENT_TO_SUPPLIER → {CONFIRMED, CHANGE_REQUESTED,
UNABLE_TO_FULFIL}`, `CONFIRMED → PREPARING`, `PREPARING → OUT_FOR_DELIVERY`,
`OUT_FOR_DELIVERY → DELIVERED`. Helpers: `hold`, `release` (→ `PENDING_VERIFICATION`),
`cancel`, `auto_complete` (`DELIVERED → COMPLETED`, system actor).

---

## J. "Verification is the approval" (`address_verification_service.verify_and_release`)

Marking the delivery address **VERIFIED** is the one routine human checkpoint. Then:

- readiness unmet (`readiness_service.check`: verified address, supplier, delivery date,
  office location, quantity ≥ 1, employee name) → `REQUIRES_ATTENTION`, typed;
- readiness met but the order carries an exception trigger
  (`ADDRESS_MANUALLY_CORRECTED` / `SHORT_NOTICE_LEAD_TIME` / `QUANTITY_CHANGED`) or
  `auto_release_enabled` is off → `REQUIRES_REVIEW`, one click from release;
- readiness met and unflagged → **auto-released** to the supplier (`SENT_TO_SUPPLIER`,
  system actor, outbound email).

VERIFIED is refused (409) for an order with **no delivery destination at all** — no
`office_location` and no `delivery_address_*`. `AddressVerificationStatus` is P&C-manual,
never set by automation, and never triggers employee contact.

---

## K. Supplier fulfilment + issues

Portal actions map to `SUPPLIER_DRIVABLE`. **Accept** merges the old acknowledge+confirm
(`SENT_TO_SUPPLIER → CONFIRMED`). `DELIVERED` auto-completes. A supplier's structured
**Report a problem** creates a typed `OrderIssue` (`CHANGE_REQUEST` / `CANNOT_FULFIL` /
`DELIVERY_ISSUE` / `OTHER`); only `CANNOT_FULFIL` moves status (`→ UNABLE_TO_FULFIL`). Issue
lifecycle (`OPEN` / `RESOLVED`) is separate from order lifecycle — an order can be
`PREPARING` with an OPEN non-blocking issue.

---

## L. Supplier communication (Unified Timeline)

`SupplierCommunication` is the canonical per-order conversation record across **both
channels, both directions**:

- **Portal**: supplier ⇄ internal messages on an order.
- **Email — outbound**: order released / changed post-release / cancelled + ad-hoc; each
  attempt is an append-only row; automatic retry with backoff; duplicate-send guarded.
- **Email — inbound**: replies polled (~10 min) from a shared mailbox via
  `get_inbound_mail_client()` (`MockInboundMailClient` in DEV + a dev inject endpoint;
  `GraphInboundMailClient` in UAT+); correlated by `order_reference` regex / `In-Reply-To`
  vs a sent `message_id`; **sender must be an ACTIVE `SupplierUser` / supplier primary
  contact** of that order's supplier; matched → `SupplierCommunication(channel=EMAIL,
  direction=INBOUND)` + internal notification, **no auto `OrderIssue`**; unmatched →
  quarantined `inbound_email` row + an internal "Unmatched supplier email" queue; never
  mutates order state from free text.

The Order Detail page renders one **Unified Timeline** merging `SupplierCommunication` +
`OrderEvent` + `OrderIssue` markers, audience-filtered (internal sees `INTERNAL_NOTE` and
raw events; the supplier portal does not).

---

## M. Attention / SLA + notifications

A daily **attention sweep** job computes and emits (deduped, digested) internal
notifications via `broadcast_notification("birthday", "BIRTHDAY_ADMIN", …)`:

| Rule | Condition |
|---|---|
| Verification overdue | `verify_by < today` and not VERIFIED |
| Supplier not accepted | `released_at < now − acknowledgement_sla_hours` and `SENT_TO_SUPPLIER` |
| Delivery at risk today | `delivery_date == today` and status ∉ {OUT_FOR_DELIVERY, DELIVERED, COMPLETED} |
| Overdue delivery | `delivery_date < today` and not terminal |
| Send failed | `EMAIL_FAILED` and auto-retry exhausted |
| Detection not running | last scan age > 26 h or `DEFERRED_SOURCE_UNAVAILABLE`; consecutive count escalates |

Supplier-facing notifications in Phase 1 are **email only**. Scan success is silent.

---

## N. User persona matrix

| Persona | App | Dashboard | Orders | Suppliers | Verify / review | Portal fulfilment | SupplierUser admin |
|---|---|---|---|---|---|---|---|
| **INTERNAL ADMIN** (`BIRTHDAY_ADMIN`) | birthday-web | ✅ | ✅ | ✅ | ✅ verify / confirm-release / hold | — | ✅ CRUD + Entra link |
| **INTERNAL USER** (`BIRTHDAY_USER`) | birthday-web | ✅ | ✅ read | ➖ | ➖ | — | ➖ |
| **SUPPLIER** (`BIRTHDAY_SUPPLIER`) | birthday-supplier-web | ✅ own | ✅ own (fulfilment fields) | — | — | ✅ accept → deliver, raise issue, message | — |

Permission keys: `birthday.dashboard.read`, `birthday.orders.{read,create,update,delete,verify,review,hold_release,cancel,send_supplier}`, `birthday.suppliers.{read,manage}`, `birthday.config.manage`, `birthday.portal.{access,respond}`.

---

## O. Deployment / configuration state

| Setting | DEV | UAT / PROD |
|---|---|---|
| `INTEGRATIONS_MODE` | `live` (People via `people-api`) — the Phase 1 validation switch | `live` |
| `EMAIL_SENDING_MODE` | `mock` (`MockGraphEmailClient` + `MockInboundMailClient`) | `live` — enabled + proven in UAT (Graph app reg + `Mail.Send` + `Mail.Read` + admin consent + shared mailbox + KV secrets) |
| `SUPPLIER_AUTH_MODE` | `entra` | `entra` |
| Jobs | `birthday-scan-job` (`30 5 * * *`), `birthday-attention-job` (daily), `birthday-comms-job` (~10 min: outbound-retry + inbound-poll) | same |

Rollback levers: `SUPPLIER_AUTH_MODE=dev`, `EMAIL_SENDING_MODE=mock`,
`INTEGRATIONS_MODE=mock`; redeploy to the prior image digest.

---

## P. Database ownership

`birthday-api` is the **only** writer of `birthday_dev`. No cross-service DB access, no
cross-service SQL joins. People facts live in `people_dev` (owned by `people-api`) and reach
Birthday only as HTTP DTOs, snapshotted onto orders at detection time.

---

## Q. Known limitations / Phase-2 items

- Real Graph outbound + inbound email is enabled and proven in **UAT**, not DEV.
- Inbound-email **attachments** are withheld (recorded, not stored) — Phase 2.
- No supplier-facing in-app notification centre — Phase 2 (email + portal pull counts today).
- No management reporting view (cakes/month, on-time %) — Phase 2.
- Teams is not a supplier channel; an internal Teams notification mirror is optional/deferred.
