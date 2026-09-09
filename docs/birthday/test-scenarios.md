# DijiBirthday — Manual Test-Scenario Catalog

Phase 1 + Phase 1.5. A single reference for walking every path in the internal
DijiBirthday app and the external Supplier Portal by hand. Each row is one
scenario: **ID · Scenario · Pre-conditions · Steps · Expected result · Pass/Fail**.

- **Internal app** = `birthday-web`, reached through `shell-web` at `/birthday/*`.
- **Supplier Portal** = `birthday-supplier-web` (its own origin, Entra B2B / dev persona).
- "Admin" = a session with `BIRTHDAY_ADMIN`; "Viewer" = `BIRTHDAY_USER` (read-only-ish).
- Dev/hosted DEV: `EMAIL_SENDING_MODE=mock` (no real mail), `INTEGRATIONS_MODE=live`
  (real People data), supplier auth `SUPPLIER_AUTH_MODE=dev` unless noted.
- Where a row says "regression test", an automated test in `apps/birthday-api/tests/`
  or a web `__tests__/` folder already covers the same assertion — the manual step is
  the human confirmation.

Legend for Pass/Fail column: `P` / `F` / `N/A` / blank (not yet run).

---

## 1. Detection & eligibility

| ID | Scenario | Pre-conditions | Steps | Expected result | P/F |
|---|---|---|---|---|---|
| DET-01 | In-window birthday creates one order | An active employee with a valid hire date and a birthday inside the scan window; no order yet | Run `birthday-scan-job` (or `/birthday/upcoming` → **Run Detection**) | Exactly one `BirthdayOrder` created, status `PENDING_VERIFICATION` (or an exception state, see §2), employee facts snapshotted onto the order | |
| DET-02 | Out-of-window birthday is ignored | Active employee whose next birthday is beyond the forward window | Run detection | No order created for that employee | |
| DET-03 | Idempotent re-scan | DET-01 has run once | Run detection again immediately | No second order; `UniqueConstraint(employee_id, birthday_year)` holds; scan run records 0 created | |
| DET-04 | Future starter | Employee hired *after* this year's birthday occurrence | Open `/birthday/upcoming` | Row present, `eligible = false`, reason `FUTURE_STARTER`, Cake Order Status "No order yet"; detection creates no order | |
| DET-05 | Inactive / terminated employee | Employee `employment_status ≠ Active` | Open `/birthday/upcoming`; run detection | Employee absent from the list; no order created | |
| DET-06 | Missing hire date | Active employee, `hire_date` null | `/birthday/upcoming` | Row present, `eligible = false`, reason `MISSING_HIRE_DATE` | |
| DET-07 | Missing / malformed birthday | Employee with no or invalid birth month/day | `/birthday/upcoming` | That single record is skipped (not fatal); the rest of the list still loads; skip is audited (no PII) | |
| DET-08 | Feb-29 birthday in a non-leap year | Employee born 29 Feb; current year non-leap | Run detection | Occurrence resolves deterministically (28 Feb / 1 Mar per `delivery_date_service`), one order, delivery date shifts per DET-09 | |
| DET-09 | Weekend / non-working-day birthday → delivery shift | Birthday falls on a Sat/Sun or a day the supplier does not work | Detect + assign supplier | `delivery_date` is shifted to the nearest **prior** working day; order shows "delivery date adjusted" | |
| DET-10 | People-source outage → defer | `people-api` unavailable at scan time | Run `birthday-scan-job` | `ScanRun.status = DEFERRED_SOURCE_UNAVAILABLE`, **zero** orders created; dashboard Detection Health shows the deferral | |
| DET-11 | Self-heal after outage | DET-10 happened; `people-api` restored | Next scheduled scan runs | Missed birthdays inside the forward catch-up window are detected now; still no duplicates | |
| DET-12 | In-flight orders unaffected by outage | Orders already past detection; `people-api` down | Verify / release / deliver those orders | All steps work — they read the snapshot on the order, never a live lookup | |
| DET-13 | Auto-refresh cron time | Hosted DEV | `az containerapp job show -n people-sync-job` (and `birthday-scan-job`) | Cron `30 18 * * *` for `people-sync-job`, `0 19 * * *` for `birthday-scan-job`, `30 20 * * *` for `birthday-attention-job` (Asia/Colombo midnight-ish, expressed in UTC) | |

---

## 2. Exceptions & recovery

| ID | Scenario | Pre-conditions | Steps | Expected result | P/F |
|---|---|---|---|---|---|
| EXC-01 | `MISSING_EMAIL` | Detected employee has no work email | Open the order | Status `REQUIRES_ATTENTION`, `exception_reason = MISSING_EMAIL`; release is blocked | |
| EXC-02 | `MISSING_EMPLOYEE_NUMBER` — surfaced | Detected employee has no employee number | Open the order as Admin | Order Detail shows a **"Team Member ID needed"** card with an input + Save (regression: `test_orders_api` / OrderDetail) | |
| EXC-03 | `MISSING_EMPLOYEE_NUMBER` — recovery | EXC-02 | Enter the real Team Member ID → Save | `exception_reason` cleared; `BDAY-TMP…` reference regenerated to `BDAY-EMP…` (while never sent to a supplier); status → `PENDING_VERIFICATION`; `EMPLOYEE_NUMBER_ASSIGNED` event | |
| EXC-04 | `NO_SUPPLIER` — surfaced | No default supplier configured / none assignable | Open the order | Status `REQUIRES_ATTENTION`, `exception_reason = NO_SUPPLIER` | |
| EXC-05 | `NO_SUPPLIER` — recovery on Fulfilment Assignment | EXC-04 | Assign a supplier via Fulfilment Assignment (`PATCH`) | `exception_reason` clears immediately, `EXCEPTION_CLEARED` event, status → `PENDING_VERIFICATION` — the order stops *looking* broken (regression: `test_orders_exception_recovery.py`) | |
| EXC-06 | `NO_DEFAULT_CAKE` — recovery | Order flagged `NO_DEFAULT_CAKE`, supplier already set | Choose a catalogue item (`PATCH catalogue_item_id`) | Same as EXC-05 (regression: `test_orders_exception_recovery.py`) | |
| EXC-07 | Exception NOT cleared while blocker remains | Order flagged `NO_SUPPLIER`, still no supplier | `PATCH` an unrelated field (e.g. delivery date) | `exception_reason` stays `NO_SUPPLIER`, status stays `REQUIRES_ATTENTION` (regression: `test_orders_exception_recovery.py`) | |
| EXC-08 | `ON_HOLD` — guided panel | Lead time shorter than the supplier needs | Open the order as Admin | An **"On hold — lead time is too short"** panel with three buttons: **Expedite anyway**, **Change delivery date**, **Cancel order** | |
| EXC-09 | `ON_HOLD` → Expedite anyway | EXC-08 | Click **Expedite anyway** | Order → `PENDING_VERIFICATION`; at verify time the short-notice flag routes it to `REQUIRES_REVIEW` (correct, not a loop) | |
| EXC-10 | `ON_HOLD` → Change delivery date | EXC-08 | Click **Change delivery date**, pick a date with enough lead time, save | Order leaves `ON_HOLD`; normal verification flow resumes | |
| EXC-11 | `ON_HOLD` → Cancel order | EXC-08 | Click **Cancel order**, confirm | Order → `CANCELLED`; appears as a tombstone; no supplier email (never sent) | |
| EXC-12 | `SHORT_NOTICE` at verify | Order with a tight but not impossible lead time | Verify the address | Order → `REQUIRES_REVIEW` (human confirm-release), not auto-released | |

---

## 3. Address verification

| ID | Scenario | Pre-conditions | Steps | Expected result | P/F |
|---|---|---|---|---|---|
| ADDR-01 | Confirm address as-is → auto-release | Order `PENDING_VERIFICATION`, deliverable address present, standard lead time, no flags | Verify → confirm unchanged | Order auto-releases → `SENT_TO_SUPPLIER`; supplier email queued (mock); `address_verification_status = VERIFIED` | |
| ADDR-02 | Correct the address → review | Same, but the operator edits address fields during verify | Verify → change a field → save | Order → `REQUIRES_REVIEW`; a human must confirm-release | |
| ADDR-03 | No deliverable address at all | Order with no office location and no delivery address lines | Attempt verify | `409` with a clear message; order stays `PENDING_VERIFICATION` | |
| ADDR-04 | Verification overdue | Order `PENDING_VERIFICATION` older than the SLA | Open dashboard | "Verification overdue" tile count includes it; attention digest lists it | |
| ADDR-05 | Office delivery (no home address) | Employee delivered to office; mock/live employee has no home address | Verify | Passes on `office_location` alone; not blocked by empty home address | |

---

## 4. Release & supplier email

| ID | Scenario | Pre-conditions | Steps | Expected result | P/F |
|---|---|---|---|---|---|
| REL-01 | Standard auto-release | ADDR-01 path | — | One `SupplierCommunication(channel=EMAIL, direction=OUTBOUND)`; order `SENT_TO_SUPPLIER`; timeline shows it | |
| REL-02 | Confirm-release after review | ADDR-02 / EXC-12 path | Open the order → **Confirm & release** | Same outbound email + transition; `REVIEW_CONFIRMED` event | |
| REL-03 | Duplicate send is a no-op | Order already `SENT_TO_SUPPLIER` | Click **Resend** once with no changes / trigger release again | No duplicate order email; idempotent; timeline not spammed | |
| REL-04 | Transient send failure → retry → recovery | (mock) force a transient failure | Release | Retried with backoff; on success the order still ends `SENT_TO_SUPPLIER`; one delivered email | |
| REL-05 | Retry exhaustion → notify + exception | (mock) force permanent failure | Release | Order flagged; internal notification raised; no partial/going-silent state | |
| REL-06 | Post-release change → supplier notified | Order `SENT_TO_SUPPLIER` or later | Admin edits supplier or delivery date | Order re-flagged for a human look; a change email goes to the supplier; `SUPPLIER_ASSIGNED` / change event | |
| REL-07 | Post-release cancel → supplier notified | Order `SENT_TO_SUPPLIER` or later | Admin cancels | `CANCELLED`; cancellation email to the supplier; tombstone in both apps | |

---

## 5. Supplier fulfilment (Supplier Portal)

| ID | Scenario | Pre-conditions | Steps | Expected result | P/F |
|---|---|---|---|---|---|
| SUP-01 | Accept → prepare → out for delivery → delivered → auto-complete | Order `SENT_TO_SUPPLIER` visible to this supplier | Walk each button in order | Each transition succeeds; `DELIVERED` auto-progresses to `COMPLETED`; timeline + internal notifications update | |
| SUP-02 | Every allowed edge has a button | Order at each supplier-drivable status | Open the order | The exact next-status button(s) from `SUPPLIER_DRIVABLE_TARGETS` are shown — no status with an allowed transition and no button | |
| SUP-03 | Rejected edge → 409 | Order `SENT_TO_SUPPLIER` | Attempt (via API) to jump straight to `DELIVERED` | `409` with a helpful message; status unchanged | |
| SUP-04 | Report a problem — each type | Any visible order | **Report a Problem** → each of Change request / Cannot fulfil / Delivery problem / Other | One `OrderIssue` of that type, status `OPEN`; internal notification; **no** status change except SUP-05 | |
| SUP-05 | `CANNOT_FULFIL` | Visible order | Report a problem → "Cannot fulfil this order" | Issue raised; order → `UNABLE_TO_FULFIL`; internal attention | |
| SUP-06 | Cancelled order shows as tombstone | Order cancelled internally (REL-07) | Supplier opens it | Read-only tombstone, no action buttons, reason visible | |
| SUP-07 | Change request → internal "Resolve & notify" | Supplier raised a `CHANGE_REQUEST` / `DELIVERY_ISSUE` | Admin opens the order → Issues card → **Resolve & notify supplier**, type the resolution | Issue → `RESOLVED`; a message + email with the resolution text goes to the supplier; timeline shows both | |

---

## 6. Communication

| ID | Scenario | Pre-conditions | Steps | Expected result | P/F |
|---|---|---|---|---|---|
| COM-01 | Internal → supplier portal message | Released order | Admin posts a message (`also_email` off) | `SupplierCommunication(PORTAL, OUTBOUND)`; supplier sees it in the order timeline; no email | |
| COM-02 | Internal → supplier message + email | Released order | Admin posts with **also email** | Portal entry **and** `EMAIL, OUTBOUND`; mock email recorded | |
| COM-03 | Supplier → internal reply (portal) | Released order | Supplier types in the timeline reply box → Send | `PORTAL, INBOUND`; internal notification; appears on the internal Unified Timeline | |
| COM-04 | Audience filter | Order with internal notes + audit + supplier messages | Compare internal timeline vs supplier timeline | Supplier timeline **excludes** internal-only notes and audit entries; internal timeline shows everything | |
| COM-05 | Inbound email matched by order reference | Released order; supplier is an ACTIVE `SupplierUser` / primary contact | Ingest an email whose body contains `BDAY-EMP…-…-…` | Exactly **one** `SupplierCommunication(EMAIL, INBOUND)` + internal notification; **no** auto `OrderIssue` (regression: `test_inbound_email.py`) | |
| COM-06 | Inbound email matched by `In-Reply-To` | An outbound email exists on a thread | Ingest a reply carrying that `Message-ID` in `In-Reply-To` | Correlated to the same order; if the outbound was tied to an issue, the inbound inherits `issue_id`; still no *new* issue | |
| COM-07 | Wrong sender → quarantine | Email from an address that is not an ACTIVE supplier contact | Ingest | `inbound_email` quarantine row; shows in **Unmatched supplier email**; no order touched | |
| COM-08 | Cross-supplier reference → quarantine | Email quotes an order reference belonging to a different supplier than the sender | Ingest | Quarantined, not linked | |
| COM-09 | No order reference → quarantine | Email with no resolvable reference and no `In-Reply-To` | Ingest | Quarantined | |
| COM-10 | Duplicate `Message-ID` → skip | COM-05 already ingested a message | Ingest the same `Message-ID` again | Skipped; no duplicate row; watermark unaffected | |
| COM-11 | Link an unmatched email by **order reference** | A quarantined email in the Unmatched queue | **Link to an order** → type `BDAY-EMP239-2026-00001` (not the numeric id) → Link | Resolves the reference; promotes to one `EMAIL, INBOUND`; row → `LINKED` (regression: `test_inbound_email.py`, `inbound-emails.test.tsx`) | |
| COM-12 | Link by numeric id still works | Quarantined email; operator knows the id | Link → type `42` → Link | `order_id:42` sent; linked | |
| COM-13 | Link with unknown reference | Quarantined email | Link → type a non-existent reference | `404`; row stays `UNMATCHED`; clear error | |
| COM-14 | Link with "Also raise an issue" | Quarantined email | Link → tick **Also raise an issue** → Link | Linked **and** one `OrderIssue` created (only because the operator chose to) | |
| COM-15 | Dismiss an unmatched email | Quarantined email | **Dismiss** | Row → `DISMISSED`; leaves the queue; no order touched | |
| COM-16 | Poll advances the watermark | — | Run the inbound poll twice | Second poll only processes messages newer than the stored watermark | |

---

## 7. Isolation & authorization

| ID | Scenario | Pre-conditions | Steps | Expected result | P/F |
|---|---|---|---|---|---|
| AUTH-01 | Supplier A cannot list supplier B's orders | Orders for two suppliers | A's session → `GET /portal/orders` | Only A's orders; B's absent (regression: `test_supplier_portal.py`) | |
| AUTH-02 | Supplier A cannot read B's order by id | — | A's session → `GET /portal/orders/{B_id}` | `404` | |
| AUTH-03 | Supplier A cannot act on B's order | — | A's session → `POST /portal/orders/{B_id}/accept` | `404` | |
| AUTH-04 | `supplier_id` cannot be chosen via request | — | Smuggle a `supplier_id` into a portal request body/query | Ignored entirely; scope is from the token claim only | |
| AUTH-05 | Inactive `SupplierUser` mid-session | A's user set `INACTIVE` after login | Next request with the still-valid token | `403` (scope re-checks the DB row every request) | |
| AUTH-06 | Inactive `Supplier` | Supplier row `INACTIVE` | Any portal request | `403` / access refused | |
| AUTH-07 | Dev persona routes under `entra` mode | `SUPPLIER_AUTH_MODE=entra` | Hit the dev persona picker route | `404` — dev shortcut is off in entra mode | |
| AUTH-08 | Viewer cannot mutate | `BIRTHDAY_USER` session | Try to PATCH an order / assign a supplier / impersonate | `403` on every mutating call | |
| AUTH-09 | Read-only impersonation — mint | Admin on a Supplier Detail page, an ACTIVE supplier user | **View portal as this user** | New tab opens the real portal signed in as that user (token via POST form, not URL); 30-min expiry (regression: `test_supplier_impersonation.py`) | |
| AUTH-10 | Read-only impersonation — banner | AUTH-09 done | Look at the portal chrome | Sticky "Viewing as … — read-only internal preview. Sign out to exit." banner on every page (regression: `app-shell.test.tsx`) | |
| AUTH-11 | Read-only impersonation — actions hidden | AUTH-09 done | Open an order + its timeline | Accept / status / Report-a-Problem buttons and the reply box are hidden; a "Read-only preview — actions are disabled" note is shown (regression: `order-timeline.test.tsx`) | |
| AUTH-12 | Read-only impersonation — server still fails closed | AUTH-09 done | Force a mutating call with the read-only token (dev tools / curl) | `403` — the token lacks `birthday.portal.respond` (regression: `test_supplier_impersonation.py`) | |
| AUTH-13 | Impersonation of an inactive user refused | Admin, a supplier user that is not ACTIVE | **View portal as** | `409`; no token minted | |
| AUTH-14 | Impersonation requires `birthday.suppliers.manage` | Viewer | Call the impersonate endpoint | `403` | |
| AUTH-15 | Exit impersonation | In a read-only preview | **Sign out** | Returns to the login screen; the read-only token is discarded | |

---

## 8. Dashboards & tables

| ID | Scenario | Pre-conditions | Steps | Expected result | P/F |
|---|---|---|---|---|---|
| DASH-01 | Every internal dashboard tile navigates | Dashboard with non-zero counts | Click each tile | Each opens `/orders` (or `/upcoming`, `/inbound-emails`) filtered to what it counts — no dead tile (regression: `dashboard-tiles.test.tsx`) | |
| DASH-02 | "Deliveries today at risk" → `?due=today` | — | Click it | Cake Orders list filtered to today's non-terminal deliveries | |
| DASH-03 | "Overdue deliveries" → `?due=overdue` | — | Click it | List filtered to past-due non-terminal deliveries | |
| DASH-04 | "Upcoming (14 days)" → `/upcoming` | — | Click it | Upcoming Birthdays page | |
| DASH-05 | Upcoming Birthdays card row click | Dashboard, ≥1 upcoming order | Click anywhere on a row | Opens `/orders/{id}`; the StatusBadge stays visible inside the row (regression: `dashboard-tiles.test.tsx`) | |
| DASH-06 | Cake Orders `due` filter control | `/orders` | Set **Delivery Due** = Today / Tomorrow / Overdue | List updates; terminal orders never appear regardless of their date (regression: `test_orders_due_filter.py`) | |
| DASH-07 | Cake Orders `due` bad value | — | `GET /api/birthday/orders?due=yesterday` | `422` (regression: `test_orders_due_filter.py`) | |
| DASH-08 | Saved views "Due today" / "Overdue delivery" | `/orders` | Click each saved-view button | Sets `due` (not `status_filter`) and reloads the list | |
| UPC-01 | Upcoming Birthdays — sort Birthday | `/upcoming`, mixed birthdays | Click the **Birthday** header, toggle direction | Rows reorder by MM-DD ascending then descending (regression: `test_directory_sort_filter.py`) | |
| UPC-02 | Upcoming Birthdays — sort Cake Order Status | Same, some with orders | Click the **Cake Order Status** header | Rows reorder by status string; "No order yet" grouped at one end (regression: `test_directory_sort_filter.py`) | |
| UPC-03 | Upcoming Birthdays — filter Cake Order Status | Some rows with orders, some without | Set the Cake Order Status `Select` to "No order yet" then to a real status | List filters to just those (regression: `test_directory_sort_filter.py`) | |
| UPC-04 | Upcoming Birthdays — search by order reference | ≥1 row has an order reference | Type part of a reference into search | Only the matching row(s) remain (regression: `test_directory_sort_filter.py`) | |
| UPC-05 | Upcoming Birthdays — whole-row click | Row that has an order | Click anywhere on the row | Opens `/orders/{order_id}` | |
| UPC-06 | Upcoming Birthdays — non-clickable row | Row with no order | Click the row | Nothing navigates; "No order yet" shown, cursor is default | |
| UPC-07 | Upcoming Birthdays — pagination + empty state | More rows than one page / a filter that matches nothing | Page through; then over-filter | Pagination works; "no results" empty state renders with the filters still visible | |
| SPT-01 | Supplier dashboard bands | Supplier with orders across states | Open the portal dashboard | Three bands: **Needs your attention** (New, Due today, Overdue, Open problems), **In progress** (Due tomorrow, Preparing, Out for delivery), **Done** (Completed today) | |
| SPT-02 | Supplier dashboard deep-links | SPT-01 | Click each tile | Opens `/orders` with the right `?status_filter=` / `?due=` — every tile navigates | |
| SPT-03 | Supplier orders — sort each column | Portal `/orders` | Click Reference / Recipient / Delivery Date / Status headers, toggle direction | Server-side sort applies for each; default is delivery date ascending | |
| SPT-04 | Supplier orders — status filter | Portal `/orders` | Choose a status in the filter `Select` | List filtered; a comma-list from a deep-link (e.g. `PREPARING,OUT_FOR_DELIVERY`) also works (regression: `test_orders_due_filter.py`) | |
| SPT-05 | Supplier orders — due filter | Portal `/orders` | Choose Today / Tomorrow / Overdue | List filtered, scoped to this supplier only (regression: `test_orders_due_filter.py`) | |
| SPT-06 | Supplier orders — search | Portal `/orders` | Type into search | Matches reference / recipient | |
| SPT-07 | Supplier orders — whole-row click | Portal `/orders` | Click a row | Opens `/orders/{id}` | |
| SPT-08 | Supplier orders — all statuses in one table | Supplier with terminal + active orders | Open `/orders` with no filter | Every order regardless of status is listed; filters/sort/search are available (the original complaint) | |

---

## 9. People refresh

| ID | Scenario | Pre-conditions | Steps | Expected result | P/F |
|---|---|---|---|---|---|
| PPL-01 | Freshness line shown | Hosted DEV (`INTEGRATIONS_MODE=live`), Admin or Viewer | Open `/upcoming` | A line: "Team-member data auto-refreshes from BambooHR every day (~midnight)" + last-refreshed timestamp | |
| PPL-02 | "Refresh now" (admin) | Hosted DEV, Admin | Click **Refresh now** | `202`; a "refresh started" hint; freshness timestamp advances within a minute (regression: `test_people_refresh.py`) | |
| PPL-03 | "Refresh now" hidden for non-admin | Viewer | Open `/upcoming` | No **Refresh now** button; the API returns `403` if forced (regression: `test_people_refresh.py`) | |
| PPL-04 | Mock mode is graceful | Local dev (`INTEGRATIONS_MODE=mock`) | `GET /api/birthday/people/freshness` | `{ available: false, auto_refresh: "daily", … }` — not a 5xx (regression: `test_people_refresh.py`) | |
| PPL-05 | Detection ≠ refresh wording | `/upcoming` | Read the two controls | "Run Detection" (create cake orders from already-refreshed data) is clearly distinct from "Refresh now" (pull from BambooHR) | |

---

## 10. Navigation & shell

| ID | Scenario | Pre-conditions | Steps | Expected result | P/F |
|---|---|---|---|---|---|
| NAV-01 | "DijiOne Home" from DijiBirthday | In `/birthday/*` | Click **DijiOne Home** in the top bar | Lands on DijiOne Home (`/`) | |
| NAV-02 | "DijiOne Home" from other modules | In DijiTalentFlow / Admin | Click **DijiOne Home** | Same — the control is in the shared `TopNav`, so every module has it | |
| NAV-03 | Home control is discoverable | Any module | Look at the top bar at ≥ `sm` width | Icon **and** "DijiOne Home" label visible (icon-only below `sm`) | |
| NAV-04 | Supplier Portal home/nav | Portal, signed in | Use the Dashboard / Orders nav | Both work; no link back into the internal app (portal is standalone) | |

---

## 11. Regression-test index

Automated coverage added for the Phase 1.5 dead-end fixes and new affordances:

| Area | File |
|---|---|
| `due` filter (internal + supplier), `status_filter` comma-list | `apps/birthday-api/tests/test_orders_due_filter.py` |
| Upcoming Birthdays sort (birthday, cake status), `cake_status_filter`, order-ref search | `apps/birthday-api/tests/test_directory_sort_filter.py` |
| People freshness + manual refresh proxy, permission gating | `apps/birthday-api/tests/test_people_refresh.py` |
| Read-only supplier impersonation end-to-end | `apps/birthday-api/tests/test_supplier_impersonation.py` |
| §H2 exception auto-clear on Fulfilment Assignment | `apps/birthday-api/tests/test_orders_exception_recovery.py` |
| §H4 link unmatched inbound email by reference / id / unknown | `apps/birthday-api/tests/test_inbound_email.py` |
| Dashboard tiles are links; Upcoming Birthdays row → order | `apps/birthday-web/src/app/__tests__/dashboard-tiles.test.tsx` |
| Link-by-reference UI | `apps/birthday-web/src/app/__tests__/inbound-emails.test.tsx` |
| Read-only banner shown / hidden | `apps/birthday-supplier-web/src/app/__tests__/app-shell.test.tsx` |
| Read-only hides the reply box | `apps/birthday-supplier-web/src/app/__tests__/order-timeline.test.tsx` |
