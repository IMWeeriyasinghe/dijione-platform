# Diji On-site — Identity Management (verified ZKBioTime ID ↔ BambooHR mapping)

**Audience:** On-site administrators, HR/IT reviewers and the engineers who
release Diji On-site. **Status:** implemented on `feat/onsite-identity-mapping`
(not yet deployed). Architecture: *Identity Architecture Review, revision 3*
(approved 2026-11-14).

## 1. The rule

A ZKBioTime **biometric ID** (what the terminal records) and a **BambooHR
employee** are separate identifiers. Diji On-site links them only through an
**administrator-verified mapping** with an explicit, inclusive, site-local
ownership period:

> A punch of ZKBioTime ID *X* on day *D* belongs to employee *E* **only if**
> exactly one verified mapping says *X* belonged to *E* on *D*.

- BambooHR **Employee Number** equality is never evidence and never used for
  attribution. It is shown to administrators only as a labelled *unverified
  hint* and is never pre-selected.
- No name or fuzzy matching. No automatic mapping, ever.
- Raw attendance events are never changed. Identity is resolved when a page is
  read, so a verified mapping affects past and future days at once, but only
  inside its period.

| Term (UI label) | Meaning | Key? |
|---|---|---|
| **ZKBioTime ID** | Biometric code on the terminal (`emp_code`, verbatim) | Source key |
| **BHR Employee ID** | BambooHR's stable record id (`bamboohr_id`) | **The identity key** |
| **BambooHR Employee Number** | HR-maintained number; may be blank, shared or change | Reference only |
| **Employee Name** | From the Workforce Directory (people-api) | Display |
| **Mapping Status** | Verified / Verified · not in directory / Unmapped / Mapping conflict | Display |

## 2. What people see

| Surface | Verified punches | Unmapped / conflicting punches |
|---|---|---|
| Overview, Today, Activity, Employees, Exceptions, profiles, photos, search | Attributed to the verified employee. One row and one headcount per employee, even with several IDs. | **Not shown.** Not counted in identified KPIs. |
| Excel exports | Included, with ZKBioTime ID(s), BHR Employee ID, BambooHR Employee Number and Mapping Status columns | Excluded; the Summary sheet states "Unmapped punches excluded: N" |
| Overview "Unmapped IDs" tile (Site Health / Identity readers) | — | Count of unmapped IDs and excluded punches |
| **Identity Management** (`/onsite/admin/identity`, admin only) | Mappings, history, conflicts | Unmapped IDs, per-day investigation, readiness |

Raw events are always kept and mirrored. Ingestion monitoring (Site Health,
freshness) is separate from identified attendance.

## 3. Permissions and audit

| Permission | Holder | Allows |
|---|---|---|
| `onsite.identity.read` | ONSITE_ADMIN | Open Identity Management: unmapped IDs, mappings, conflicts, history, readiness, investigation |
| `onsite.identity.manage` | ONSITE_ADMIN | Every change: map, end, correct, reassign, reject, withdraw, import |

Every change:
- is enforced by onsite-api, whatever the UI shows;
- is limited to sites the caller has enabled. Records of other sites behave as
  if they don't exist (404);
- requires a written reason or evidence of at least 10 characters;
- writes an `onsite_identity_events` row in the **same transaction**: action,
  actor, time, before/after state, note;
- sends a Platform audit event (`onsite.identity.*`, best effort; the local
  history is the durable record).

Records are never deleted. Corrected mappings become `SUPERSEDED`; withdrawn
rejections become `WITHDRAWN`.

Emergency freeze: `ONSITE_IDENTITY_WRITES_ENABLED=false` blocks every change
(503); reading continues.

## 4. Administrator procedures

### 4.1 New employee enrolment (the normal flow)
1. IT enrols the person on the terminal with a **new, unused** ZKBioTime ID.
   They punch from day one.
2. Until HR completes BambooHR and an admin maps the ID, those punches are held
   as **unmapped**. They are kept, but not shown to viewers.
3. When the BambooHR record exists, open **Identity Management → Unmapped IDs**,
   find the ID, and choose **Map…**.
4. Type a name, BHR Employee ID or Employee Number to search the directory.
   Nothing is pre-selected; pick the right person.
5. Enter **Owned from**, the first day the ID belonged to this person, taken
   from the enrolment record. It is never assumed from the first punch.
   Leave **Owned until** empty for ongoing ownership.
6. Write the evidence (e.g. "IT enrolment sheet 2026-11-01, confirmed by HR").
7. Read and tick **each** warning, for example: earlier punches stay unmapped,
   starts before the hire date, the employee is inactive, the employee already
   has other IDs, this ID was used by someone else before.
8. Check the confirmation sentence, then **Confirm mapping**. The person's past
   punches from the start date appear on every page immediately.

### 4.2 Several IDs for one person
Map each ID to the same employee. Every page counts the person once, and their
profile lists every ID with its period.

### 4.3 Ending ownership (leaver, lost card, retired ID)
**Mappings → End…** with the last owned day. Attendance up to that day stays
with the employee; later punches become unmapped. To change an end date that is
already set, use **Correct…**.

### 4.4 Reassigning an ID to someone else
**Mappings → Reassign…**: the new owner's start date, the employee, a reason and
evidence. The previous owner keeps every day before that date, and the two
periods never overlap. If the ID has punches **on** the handover day, the system
will not split the day. You must choose one of:
- **Leave that day unmapped** (recommended when unsure). It appears under
  *Conflicts & history → Ambiguous reassignment days*.
- Attribute the day to the new owner.
- Attribute the day to the previous owner.

### 4.5 Correcting a wrong mapping
**Mappings → Correct…** with a reason. Only that mapping's days lose their
attribution. You can add a replacement owner and period in the same step, with
its own evidence and warnings. The old record stays in history as *Superseded*.

### 4.6 "This ID is not this person"
**Unmapped IDs → Not this person…** records a rejection, for all history or a
date range. A rejection never attributes anything. It stops that pairing being
hinted or mapped in that period. **Withdraw…** (with a reason) under *Conflicts
& history* if it was entered in error.

### 4.7 Investigating an ID
**Investigate** shows each day's punches for the ID, who (if anyone) they are
attributed to, every mapping and rejection, and any hint.

### 4.8 HR-approved bulk import
1. HR prepares a UTF-8 CSV with **exactly** these columns:
   `site_id, zk_emp_code, bamboohr_id, valid_from, valid_to, evidence, verified_by, verified_on, source_reference`.
   Any other file, including the raw HR workbook, is rejected.
2. **Import → Dry run.** The file is validated row by row by simulating the
   whole import, which is then rolled back. Nothing is saved.
3. A row missing its evidence, verifier, verification date or source reference
   is an **error**. So are an unknown employee, an overlap and a rejected pair.
   Nothing can be applied while any error remains.
4. Warnings must be reviewed with HR and acknowledged.
5. **Apply** needs the dry run of the same file by the same administrator from
   the last 30 minutes. The batch is **all-or-nothing**: if any row fails, no
   mapping and no history row is kept.
6. Imports are per environment. Never copy mappings between databases.

## 5. Readiness (before a production cutover)

**Identity Management → Readiness** shows, for the last 30 days:
- identified vs total punches;
- identified employees and active IDs;
- unmapped IDs and their punches;
- the 25 highest-volume outstanding IDs, each with a disposition;
- unresolved conflicts, verified mappings, mappings without evidence (must be 0)
  and import batches.

It **never** gives a pass/fail. HR/IT acceptance criteria (architecture review
§I.3):
1. every top-25 outstanding ID has a recorded disposition;
2. no unresolved conflicts;
3. the HR-approved import was applied with zero errors in that environment;
4. HR spot-checked an agreed sample of mappings against enrolment records;
5. directory data is less than 24 hours old;
6. coverage reviewed, with the threshold approved by the owner at that time;
7. the audit log shows the import and all manual mappings with their actors.

## 6. Release sequencing (DEV → UAT → PROD)

Each environment has its own mapping data. All environments read the same
attendance source, but mappings are entered (or imported) per environment and
**never promoted**.

| Step | Action |
|---|---|
| 1 | platform-api with revision `f2a4b6c8d0e2` (registers `onsite.identity.manage` for ONSITE_ADMIN) **before** onsite-api |
| 2 | onsite-api image with Alembic `0002_onsite_identity`; update the `migrate-onsite-api` job to the **same digest** and run it; `/health/deep` must show head |
| 3 | Verify the **current** onsite-web against the new API. The compatibility layer (`ONSITE_LEGACY_CONTRACT=on`) keeps the old routes and shapes, with values from verified mappings only. |
| 4 | Import the HR-approved CSV: dry run → HR/IT review → apply. Then review readiness. |
| 5 | Owner approves the threshold (production only) |
| 6 | Deploy the new onsite-web; smoke-test Overview, Today, Employees, a profile, an export and Identity Management |
| 7 | Monitor for 48 hours: readiness daily, audit events, freshness |
| 8 | After an agreed stable period, release onsite-api without the compatibility layer (`legacy_contract.py`, code-addressed routes) |

UAT: Colombo stays disabled unless separately approved, which limits UAT
acceptance to admin UI, permissions, import dry runs and migrations. Production
blockers still open: UAT/PROD bicep parameter files; PROD Colombo
`site_settings` unverified; no HR-approved mapping CSV yet.

## 7. Recovery (forward-only)

- **Never** redeploy a pre-redesign onsite-api image: it would bring back
  numeric attribution.
- **Never** run `alembic downgrade` in DEV/UAT/PROD. The downgrade exists for
  CI only. The new tables are additive.
- Problem with mapping changes: set `ONSITE_IDENTITY_WRITES_ENABLED=false`
  (reads continue) and fix forward.
- Problem with dashboards: disable the site in *Sites*. The fail-closed
  behaviour shows empty data, never wrong data. Fix forward.
- Problem with the new UI: redeploy the previous onsite-web. It still works
  against the new API while the compatibility layer is on.
- Mappings can always be exported (*Mappings → Export CSV*). The history is
  immutable.

## 8. Remaining HR/IT responsibilities

- Issue every new biometric enrolment a **new, unused** ZKBioTime ID, and record
  the date and person (the evidence for step 4.1).
- Tell On-site admins about leavers, card or ID retirements and re-issues, so
  mappings are ended or reassigned on the right day.
- Produce and sign off the HR-approved mapping CSV for each environment's first
  import, then review dispositions for high-volume unmapped IDs.
- Keep BambooHR records complete. Diji On-site never writes to BambooHR or
  ZKBioTime.

## 9. Technical reference

| Item | Location |
|---|---|
| Tables | `apps/onsite-api/app/models/identity.py` |
| Migration | `apps/onsite-api/alembic/versions/0002_onsite_identity.py` |
| Resolution | `apps/onsite-api/app/services/identity_resolution.py` |
| Admin service and import | `app/services/identity_admin_service.py`, `app/services/identity_import_service.py` |
| Admin API | `app/api/routes/identity_admin.py` (`/api/onsite/admin/identity/*`) |
| Verified employee routes | `/api/onsite/employees/by-id/{bamboohr_id}` and `/photo` |
| Compatibility layer | `app/services/legacy_contract.py` (`ONSITE_LEGACY_CONTRACT`) |
| UI | `apps/onsite-web/src/app/admin/identity/page.tsx`, `src/components/identity/dialogs.tsx`, `src/lib/identity.ts` |
| Performance run | `RUN_PERF=1 pytest apps/onsite-api/tests/perf -s` |

Rules enforced on every change:
- periods of one ID never overlap;
- dates are inclusive and site-local;
- an ID belongs to one owner per day, while one employee may hold many IDs;
- a rejection blocks its own period only;
- the employee must be in the Workforce Directory (503 when it is unavailable);
- all checks run inside one transaction, with a per-ID advisory lock on Postgres.
