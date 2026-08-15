# BambooHR Live Discovery (2026-08-14)

Read-only field survey against the real `dijitalteam` BambooHR tenant,
performed once real credentials (`BAMBOOHR_API_KEY`, `BAMBOOHR_SUBDOMAIN`)
were added to `apps/birthday-api/.env`. No BambooHR writes were made at any
point. This document is the source of truth for the field-name assumptions
baked into `app/integrations/bamboohr/http_client.py`,
`app/integrations/bamboohr/mapper.py`, and `app/services/eligibility_service.py`.

## Connection

`INTEGRATIONS_MODE=live` + real `BAMBOOHR_API_KEY`/`BAMBOOHR_SUBDOMAIN` in
`apps/birthday-api/.env` (gitignored — confirmed present in `.gitignore`;
confirmed absent from `.env.example`, which only documents the variable
*names*; confirmed absent from `birthday-web` frontend code and every
`NEXT_PUBLIC_*` variable in the repo). `app/core/config.py` loads it via
Pydantic Settings' `env_file=".env"` server-side only — the key never
crosses into a browser-visible response or log line anywhere in this
codebase.

Connection result: **successful**, via `POST
/api/gateway.php/dijitalteam/v1/reports/custom?format=JSON` (HTTP Basic,
username=API key, password=`x`). 484 employee records returned in a single
call.

## Field survey

Requested a broad candidate field list and checked which fields the tenant
actually populates (presence count out of 484 records):

| Field requested | Present | Notes |
|---|---|---|
| `id` | 484/484 | Numeric string. Used as `employee_id`. |
| `firstName` / `lastName` | 484/484 | Kept for fallback only. |
| `displayName` | 484/484 | **Used as `display_name`** — already handles preferred-name overrides, preferred over concatenating first/last. |
| `preferredName` | 400/484 | Not used — `displayName` already covers this. |
| `workEmail` | 475/484 | Some employees have no work email (matches the existing MISSING_EMAIL exception path in `detection_service`). |
| `dateOfBirth` | 484/484 | Full `YYYY-MM-DD` **with a real birth year** — deliberately never requested/stored, for privacy. |
| `birthday` | 478/484 | BambooHR's own derived `MM-DD` field, no year. **Used as the birthday source** — matches the "no birth year" design already baked into `BambooHREmployee`/`UpcomingBirthdayItem`. |
| `status` | 484/484 | Values: `Active` (326) / `Inactive` (158). **The single authoritative active/inactive field.** |
| `employmentHistoryStatus` | 474/484 | Values: `Contractor` (307), `Terminated` (158), `Full-Time` (6), `Part-Time` (3). **This is employment *type*, not active/inactive** — a naive "fall back to this field" (as the pre-live-discovery `http_client.py` draft did) would have misclassified an active Contractor as excluded. Not used for filtering. |
| `employeeStatusDate` | 474/484 | Not used. |
| `hireDate` | 484/484 | Always populated. **Used as `hire_date`.** |
| `originalHireDate` | 484/484 | Almost always the sentinel `0000-00-00` — not reliable, not used. |
| `hireDate1` | 0/484 | Does not exist for this tenant. |
| `terminationDate` | 484/484 | Real ISO date for terminated employees (158 non-sentinel, exactly matching the 158 `Inactive` count); sentinel `0000-00-00` (not null) when not terminated. **Used as `termination_date`**, with the sentinel normalized to `None` in `mapper.py`. |
| `department` | 474/484 | For this tenant (a talent/staffing company), holds the **client engagement / bench assignment** (e.g. "Internal Bench", "blueAPACHE", "Cytrack" — 130+ distinct values), not a functional org department. Passed through as-is under the `department` field name per the DTO contract — this is genuinely what "department" means for this business. |
| `division` | 458/484 | Geography/division (e.g. "Sri Lankan", "Australian \| QLD"). Not used. |
| `location` | 467/484 | Country/city (Sri Lanka: 451, Brisbane: 9, etc.). **Used as `office_location`.** |
| `jobTitle` | 474/484 | Not used (not part of the DTO contract). |
| `workLocation` | 0/484 | Does not exist for this tenant. |

## Active-employee logic — confirmed against real data

`status` is exactly two-valued for this tenant: `"Active"` / `"Inactive"`.
`list_active_employees()` filters on `status == "Active"` server-side —
never client-side, never re-derived in the frontend.

**Critical finding, confirmed live**: an employee CAN show `status=Active`
in BambooHR before their hire date. 9 of the 326 active records had
`hireDate` in the future relative to "today" (2026-08-14), e.g.
`2026-08-24`, `2026-09-01`, `2026-09-03`. This directly validates the
plan's eligibility-rule requirement — `status=Active` alone is
insufficient to determine cake-order eligibility; the hire-date check in
`eligibility_service.compute_eligibility` is not redundant with the
client-level active filter, it catches a real, observed case.

None of those 9 future starters happened to have a birthday occurring
*before* their hire date in a wide (400-day) test window against the live
tenant — i.e. no real `FUTURE_STARTER`-classified record was observed in
this dataset at survey time (their hire dates are all close enough that
their birthday, whenever it next occurs, falls after they've already
started). The `FUTURE_STARTER` code path itself is exercised by
`test_future_starter_included_but_marked_ineligible` (directory service),
`test_future_starter_never_gets_an_order` (detection service, using the
mock roster's `bhr-1012` fixture, added specifically for this), and
`test_hire_date_after_occurrence_is_future_starter` (unit test) — the rule
is proven correct even though this particular live dataset snapshot didn't
happen to contain a real example of it.

## Real-data validation results (2026-08-14, read-only)

- Connection: successful, 484 employee records returned.
- Active employees returned by `list_active_employees()`: 326.
- `GET /api/birthday/employees/upcoming-birthdays?days=30`: **24** active
  employees with an eligible upcoming birthday in the next 30 days — all
  24 were `ELIGIBLE` (no future starters or terminated-before-birthday
  cases happened to land in that specific 30-day window).
- Widened to `days=400` (covers every employee's next occurrence): **320**
  records returned, all `ELIGIBLE` — see the future-starter note above for
  why 0 `FUTURE_STARTER` records appeared in this particular snapshot.
- Missing-birthday records: 6 employees (478/484 had a populated
  `birthday` field) — correctly excluded by `list_active_employees()`
  (`_parse_birthday_field` returns `None`, and the row is skipped).
- Missing-hire-date records: 0 (`hireDate` was 484/484 populated) — the
  `MISSING_HIRE_DATE` path is therefore untested against live data, but is
  covered by unit/directory-service tests using synthetic fixtures.
- API/permission limitations encountered: **none** — the configured API
  key had full read access to the Custom Report endpoint and every
  requested field either returned data or cleanly returned empty/absent
  (no 403s on any individual field).

No BambooHR write endpoint was called at any point during this survey or
during application testing.

## Address & geography follow-up discovery (2026-08-15)

Read-only, same `dijitalteam` tenant, performed to answer two open product
questions: (1) can a real residential/delivery address be retrieved for the
address-verification workflow, and (2) is there a more meaningful
Sri-Lanka geography value than the coarse `location` field (which reads
"Sri Lanka" for the vast majority of records)?

`GET /v1/meta/fields` was queried first (400 total fields for this tenant)
to find the real field catalogue instead of guessing candidate names.
Address/geography-shaped fields found (id | name | alias | type):

| id | name | alias | type |
|---|---|---|---|
| 8 | Address Line 1 | `address1` | text |
| 9 | Address Line 2 | `address2` | text |
| 10 | City | `city` | text |
| 11 | State | `state` | state |
| 12 | Zip Code | `zipcode` | text |
| 3991 | Country | `country` | country |
| 4622 | City | `customCity` | text |
| 4623 | Province | `customProvince` | text |
| 4624 | Postal Code | `customPostalCode` | text |
| 4625 | Country | `customCountry` | text |

(`Dependent City/State/ZIP` and `Emergency Contact City/State/ZIP` were
also present but excluded — they describe a different person, not the
employee's own address.)

A live report pull requesting `id, displayName, address1, address2, city,
state, zipcode, country, customCity, customProvince, customPostalCode,
customCountry, location` against the same 484-record roster returned:

| Field | Present | Notes |
|---|---|---|
| `address1` | 482/484 | Free-text street address, e.g. "196/C, Rividewgama, Bodhiraja Mawatha, Paratta, Panadura". |
| `address2` | 468/484 | Secondary line, often empty for LK addresses. |
| `city` | 482/484 | Real city/town names — Colombo, Galle, Matara, Dehiwala, Kadawatha, Piliyandala, Gampaha, Kuliyapitiya, Awissawella, Moratuwa, Agarapathana, etc. Meaningfully granular, highly populated. |
| `state` | 474/484 | Province for LK records — Western, Southern, Central, North Western (a few blank strings). AU state (Queensland) for the Brisbane office. |
| `zipcode` | 468/484 | Populated LK postal codes (e.g. 12500, 10650, 10300, 11850). |
| `country` | 483/484 | "Sri Lanka" / "Australia". |
| `customCity` / `customProvince` / `customPostalCode` / `customCountry` | 72-77/484 | Sparse, not used — standard fields above are the reliable source. |

**Cross-tab with `location`**: for the 451 records where `location ==
"Sri Lanka"`, `city` independently holds real town names (Dehiwala,
Hanwella, Piliyandala, Kadawatha, Gampaha, Matara, Colombo, Galle,
Moratuwa, ...) and `state` holds the province. This confirms `location` is
a coarse country/office field — it is not derived from, and does not
derive, `city`/`state`.

**Conclusions, adopted in code**:
- Residential/delivery address is reliably constructible from `address1 +
  address2 (optional) + city + state + zipcode + country` and is used to
  seed a `BirthdayOrder`'s delivery-address snapshot at detection time
  (never written back to BambooHR — see `app/services/order_service.py`
  and `app/services/address_verification_service.py`).
- The Upcoming Birthdays "Location" column now displays `city` (not
  `location`/`office_location`, which remains solely the supplier-
  resolution key in `detection_service.resolve_supplier_for_office`) —
  see `app/services/directory_service.py`. `state` (province) powers a
  Location filter.
