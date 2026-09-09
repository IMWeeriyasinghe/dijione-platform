# DijiBirthday — Supplier onboarding runbook

How a new cake supplier is brought online for the DijiBirthday Supplier Portal.
Entra ID B2B guest is the **only** production authentication mechanism; **IT
controls guest invitations** — external supplier admins never invite guests.

> Two independent layers: **Entra authenticates; an ACTIVE `SupplierUser`
> authorizes.** A guest added to the tenant with no matching ACTIVE
> `SupplierUser` gets a generic 403 and no access. A `SupplierUser` is
> **never** auto-created from a sign-in.

---

## Steps

| # | Who | Action | Result / check |
|---|---|---|---|
| 1 | Internal admin (`BIRTHDAY_ADMIN`) | **DijiBirthday → Suppliers → New Supplier**: name, status ACTIVE, primary contact name + **email**, phone, escalation contact, `lead_time_days`, **working days** (e.g. `Mon-Fri`), cutoff time, notes. | Supplier row created. Working days drive the weekend / non-working-day delivery-date shift (§1.1). |
| 2 | Internal admin | On the supplier: add **≥ 1 service location** (office name), and a **catalogue** with exactly one item marked **default cake** (or no items at all — plain "Cake" is valid). | Supplier Detail **Setup readiness** panel shows *location ✓*, *default cake ✓*. |
| 3 | Internal admin | Add a **Supplier User**: full name + the **email address the person will sign in with**. Status ACTIVE, role SUPPLIER_USER / SUPPLIER_ADMIN. | `SupplierUser` row, onboarding state **NOT_INVITED**. |
| 4 | **IT / Entra admin** | In **Entra ID → Users → Invite external user**, invite that exact email as a **B2B guest** in the Dijital Team tenant (a `@dijitalteam.com` work account needs no invitation). | Guest appears in the directory as *PendingAcceptance*. |
| 5 | Internal admin | On the Supplier User, use **Mark as invited** (`mark_invited`). | Onboarding state → **INVITED** (`invited_at` stamped). |
| 6 | Supplier contact | Opens the invitation email → **Accept** → is redirected to the Supplier Portal → **Sign in with Microsoft** → completes the Microsoft prompt (MFA if the tenant requires it). | — |
| 7 | System | On first sign-in, `resolve_supplier_user` matches the verified `email` claim to the `SupplierUser` row and stamps **`entra_object_id`** (+ `linked_at`); `record_supplier_login` stamps **`last_login_at`**. | Onboarding state → **LINKED** then **ACTIVE**. The `#EXT#` rewritten UPN is never treated as an email — matching is on the verified `email` claim / the durable `oid`. |
| 8 | Supplier contact | Sees only their own supplier-scoped orders; can accept, progress fulfilment, message, and raise problems. | Isolation: a manipulated order id belonging to another supplier 404s. |

## Onboarding state (Supplier Detail → Supplier Users)

`NOT_INVITED` → `INVITED` (step 5) → `LINKED` (first `oid` link) → `ACTIVE`
(has signed in). `INACTIVE` when the row is deactivated — access is lost on
the **next** request, not at token expiry. `entra_object_id` itself is not
shown to non-admins.

## Offboarding

Set the `SupplierUser` **INACTIVE** (never hard-deleted — historical
`OrderEvent`/audit actor references stay resolvable). Optionally have IT
remove the B2B guest from the tenant. Orders stay visible to the supplier's
other ACTIVE users.

## Rollback / DEV note

`SUPPLIER_AUTH_MODE=dev` swaps steps 4–7 for the seeded-persona picker
(`/api/birthday/internal/dev/supplier-*`, 404 under `entra`). Real Graph
email (`EMAIL_SENDING_MODE=live`) and real Graph inbound polling are enabled
and proven in **UAT**, not DEV.
