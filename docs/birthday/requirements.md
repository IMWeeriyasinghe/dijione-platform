# DijiBirthday — Requirements & Scope

DijiBirthday automates employee birthday-cake ordering for Dijital Team, sourced from
BambooHR **via the People / Workforce domain (`people-api`)** — `birthday-api` never
calls BambooHR directly and never reads `people_dev`.

> **Current model (semi-automation, shipped).** DijiBirthday is a **semi-automated
> exception-based workflow**, not an approval-gated one. The system discovers upcoming
> birthdays, applies eligibility rules, creates an order, applies deterministic defaults,
> and snapshots delivery information. An internal user's one routine action is to
> **verify the delivery address**; a standard order then **auto-releases to the supplier**.
> Only orders carrying an exception trigger route through `REQUIRES_REVIEW` for a
> one-click human confirm. There is **no** `DRAFT` / `READY_FOR_APPROVAL` / `APPROVED`
> status and **no** universal approval step — those legacy statuses were retired (no
> persisted production data existed to migrate).

The authoritative end-to-end reference is `docs/birthday/end-to-end-workflow.md`. The
in-repo Phase 1 completion plan (independent review + delivery plan) is tracked at
`C:\Users\Dell\.claude\plans\dijione-dijitalentflow-rippling-cascade.md`.

---

## Architecture

| Component | Tech | Audience | Talks to |
|---|---|---|---|
| `apps/birthday-web` | Next.js | Internal staff (via `shell-web` `/birthday` zone) | `birthday-api` |
| `apps/birthday-supplier-web` | Next.js | External supplier users | `birthday-api` (`/api/birthday/portal/*` + `/api/birthday/supplier/auth/*` only) |
| `apps/birthday-api` | FastAPI | both frontends + schedulers | own DB (`birthday_dev`), `people-api` (employees), `platform-api` (identity / audit / notifications), Microsoft Graph (email — **mock in DEV**) |
| `birthday-scan-job` | Azure Container Apps Job (`30 5 * * *`) | — | `POST /api/birthday/internal/run-daily-scan` |

**Boundaries that must not be reversed:**

- No direct frontend → BambooHR or frontend → `birthday-api`-internal access.
- `birthday-api` consumes People only through `auth_client_py.EmployeeDirectoryClient`
  (`people-api`), read-only. Static guard: `tests/test_no_direct_bamboohr_dependency.py`.
  There is **no `app/integrations/bamboohr/`** — the People adapter is
  `app/integrations/people_source/`.
- `birthday-api` holds **no employee mirror table**. A `people-api` outage makes the scan
  **defer** (`ScanRun.status = DEFERRED_SOURCE_UNAVAILABLE`, zero orders) and self-heal
  next run. In-flight orders are unaffected — every employee fact is **snapshotted onto
  the order at detection time**.
- Entra ID B2B guest is the **only** production auth mechanism for supplier users
  (`docs/platform/birthday-supplier-authentication.md`). `SUPPLIER_AUTH_MODE` (`dev` |
  `entra`) is the authoritative switch — not `APP_ENV`.
- Birthday email is behind a factory seam and is **mock** in DEV regardless of other
  settings (`EMAIL_SENDING_MODE`, independent of `INTEGRATIONS_MODE`).

---

## Domain model (`apps/birthday-api/app/models/`)

`BirthdayOrder`, `Supplier`, `SupplierLocation`, `SupplierCatalogueItem`, `SupplierUser`,
`SupplierCommunication`, `OrderEvent`, `OrderIssue`, `SpecialRequirement`,
`BirthdayDetectionConfig`, `OrderSequence`, `ScanRun`.

- **Idempotent detection** — DB-level `UniqueConstraint(employee_id, birthday_year)` on
  `birthday_orders`; never a duplicate regardless of retries.
- **Order reference** — `BDAY-EMP{teamMemberId}-{year}-{seq:05d}`, where `teamMemberId` is
  BambooHR's `employeeNumber` (business Team Member ID), never the internal record id.
  An employee with **no** `employeeNumber` gets a provisional `BDAY-TMP…` reference and
  the order is flagged `MISSING_EMPLOYEE_NUMBER` (no silent fallback); supplying the real
  ID clears the exception and regenerates the reference while the order has not reached a
  supplier.
- **Address verification** — `AddressVerificationStatus` (`NOT_CHECKED` /
  `VERIFICATION_REQUESTED` / `VERIFIED` / `NEEDS_UPDATE` / `NOT_APPLICABLE`), P&C-manual,
  never set by automation, never triggers employee contact. VERIFIED is refused for an
  order with no delivery destination at all (no `office_location` and no
  `delivery_address_*`).

## Order status (`OrderStatus`, 13 active values)

`PENDING_VERIFICATION` (the one routine human gate) · `REQUIRES_REVIEW` (flagged, one-click
confirm) · `REQUIRES_ATTENTION` (typed exception queue) · `ON_HOLD` · `SENT_TO_SUPPLIER` ·
`CHANGE_REQUESTED` · `CONFIRMED` (supplier accepted) · `PREPARING` · `OUT_FOR_DELIVERY` ·
`DELIVERED` · `COMPLETED` (auto-set on delivery) · `UNABLE_TO_FULFIL` · `CANCELLED`.

Transition table + supplier-drivable subset: `app/services/order_status_service.py`. Every
transition writes an `OrderEvent` and an `AuditService.log(...)`. Legacy
`DRAFT`/`READY_FOR_APPROVAL`/`APPROVED`/`PLANNED`/`REJECTED`/`SUPPLIER_REVIEW` are retired.

---

## Detection engine (`app/services/detection_service.py`)

Window-based (not exact-N-day), configurable via the single `BirthdayDetectionConfig` row.
Per employee in-window: eligibility ladder (`eligibility_service`), lead-time class
(Normal / Short-Notice / Urgent) vs the resolved supplier's `lead_time_days`, deterministic
supplier resolution (sole ACTIVE → office-location rule → `is_default`), default-cake
resolution, `verify_by` SLA anchor, address snapshot. Initial status:
`MISSING_EMAIL` / `MISSING_EMPLOYEE_NUMBER` / `NO_SUPPLIER` / `NO_DEFAULT_CAKE` →
`REQUIRES_ATTENTION`; else `days_remaining ≥ lead_time_days` → `PENDING_VERIFICATION`, else
`ON_HOLD`.

Production detection is an **external scheduler** (`birthday-scan-job`) calling
`POST /api/birthday/internal/run-daily-scan` — there is deliberately no in-process
scheduler. `POST /api/birthday/admin/run-detection` is the auth-gated equivalent for
UAT/ops and calls the **same** service.

---

## Supplier communication

The per-order **`SupplierCommunication`** timeline is the canonical record of every message
between internal staff and a supplier, across both channels and both directions:

- **Portal** — supplier ⇄ internal messages on an order.
- **Email** — internal → supplier (order released / changed / cancelled + ad-hoc; auto-retry
  with backoff) and supplier → internal (replies polled from a shared mailbox, correlated by
  order reference / `In-Reply-To` + verified sender, quarantined on failure).

`OrderIssue` is the typed, resolvable *concern* record (`CHANGE_REQUEST` / `CANNOT_FULFIL` /
`DELIVERY_ISSUE` / `OTHER`). It is created only by a deliberate action — the supplier's
structured *Report a problem*, or an internal user linking a communication — never
auto-created from free-text email. `OrderEvent` remains canonical for the lifecycle; the
platform `AuditLog` for compliance. Order Detail renders one **Unified Timeline** merging
all of these, audience-filtered.

---

## Security (mandatory)

- Backend role/permission enforcement (`require_birthday_permission`,
  `require_supplier_permission`); frontend hiding is not authorization.
- Supplier isolation server-side: `supplier_id` from `SupplierScope` (the validated token),
  never a request parameter; a manipulated order id belonging to another supplier 404s.
- `SupplierUser.status` re-checked on every portal request, not just at token issuance.
- Inbound email: verified sender, HTML→text sanitisation, attachments withheld (Phase 2),
  idempotent on message-id, no business-state mutation from free text.
- Secrets only via environment / Key Vault; never committed.
