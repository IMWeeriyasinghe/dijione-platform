# Identity matching — the major open investigation

## The four identities (do not conflate)

| Identity | Where | Example meaning |
|---|---|---|
| ZKBioTime internal employee id | `personnel_employee.id` | DB surrogate key |
| ZKBioTime Employee Code | `personnel_employee.emp_code` = `iclock_transaction.emp_code` = Azure `EmpCode` | what the terminal records |
| BambooHR Employee Number | Workforce Directory `employee_number` (people-api) | HR identity |
| BambooHR id | Workforce Directory `bamboohr_id` | stable HR key; used for photos |

## What the code does today (verified)

`identity_match_service.py` / `dashboard_service.Identity` match **EmpCode == Employee Number by exact,
case-sensitive string equality** — no trimming, zero-stripping or name matching. Classes:
`MATCHED_ACTIVE`, `MATCHED_INACTIVE`, `MATCHED_BEFORE_HIRE`, `AMBIGUOUS` (shared number), `UNMATCHED`.
Names, departments and photos shown in the UI come from that match.

## Why that is not proof of identity

Live report (DEV/UAT, 2026-11-13, Colombo site): 399 attendance codes; 261 "matched active", **104 matched
an inactive employee**, **15 matched someone not yet hired** at the time of the activity, 19 unmatched;
directory 542 entries (21 blank numbers, 0 duplicates). Codes are small integers (1–5 digits) and Employee
Numbers are small integers too, so equal strings can be coincidence. The inactive/before-hire share strongly
suggests many matches are **collisions, i.e. wrong names/photos may be displayed today**.

## Production personnel export (2026-11-07)

Produced on the production PC with `deploy/production-pc/export-employee-directory.ps1` (DijiOnsite-Agent repo,
read-only, uses the Agent's DPAPI-protected reader credential in memory only). File
`employee-directory-20261107-001059.csv` — **never commit it; it is outside both repos**. Aggregate findings,
re-verified 2026-11-13 from the file (no personal values printed):

| Finding | Value |
|---|---|
| rows / unique internal ids / unique emp_codes | 373 / 373 / 373 |
| records with any name | **1** |
| records with email | **0** |
| `is_active` | **`f` for all 373** (including staff known to punch) — not usable as a status |
| department | one value for all rows (`Department`) |
| emp_code format | numeric, 1–5 digits; internal id equals emp_code for only 1 row |

Note: 399 codes appear in attendance vs 373 personnel rows — some codes have activity but no current
personnel record (deleted/renumbered personnel).

**Implication:** ZKBioTime itself holds no usable identity attributes. A mapping cannot be derived from it.

## Chosen approach (agreed)

Keep ZKBioTime, device user IDs and fingerprint registrations untouched. Maintain, **inside Diji On-site**, an
administrator-verified mapping `(site_id, emp_code) → bamboohr_id / Employee Number`, with:
- who verified it, when, evidence/source note, and an audit trail (platform-api audit events);
- explicit states: verified / rejected / unknown; verified mappings take precedence over string equality;
- the UI clearly marking unverified (string-equal) matches until verified — or hiding names for them
  (decision needed);
- no automatic name-similarity matching; suggestions may be shown only as unverified hints.

## Next investigation steps (not started)

1. Can real names be recovered from **the ZKBioTime application UI** (personnel screens, reports) on the
   production PC? (operator task, read-only)
2. Does the **terminal's own user list** (device user directory, names entered at enrolment) hold names?
   Export via ZKBioTime "device user" tools only — never write to the device.
3. Existing enrolment/HR records (paper/spreadsheet onboarding lists mapping fingerprint code to employee).
4. HR (BambooHR) owners confirming a code list.
Then: design the mapping table + admin UI (Identity Match page → "Verify mapping"), migration, tests.

Until then, treat names on Today/Activity/Employees as **unverified** for codes that are not obviously correct.
