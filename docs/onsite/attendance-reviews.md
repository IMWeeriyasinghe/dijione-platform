# Diji On-site — daily fingerprint activity and attendance reviews (v0.9)

## What is recorded

The office has an **entry-side fingerprint reader** and an **anonymous push-to-exit button**, so no
employee-specific exit is ever recorded. Diji On-site therefore reports only what the reader
observes:

| Term | Meaning |
|---|---|
| First / Last Recorded Fingerprint | The first and last fingerprint of an identity on a site-local day. The last fingerprint is **not an exit**. |
| Earliest / Latest Recorded Fingerprint | Overview: the first and last fingerprint of the whole site-local day over every identity (ties listed). |
| Recorded Span | Last − first recorded fingerprint of an identity-day. A measured interval between observations — not a confirmed exit, presence or hours worked. **Unavailable ("—") for a single fingerprint, never 0h.** One server calculation (`attendance_summary.recorded_span`) feeds Today, the Daily summary, Activity details and every export. |
| Single Recorded Fingerprint | Only one fingerprint that day. A neutral observation for optional review — never a violation. |

## Identity-days

`GET /api/onsite/activity/daily` returns one row per **identity-day** for every recorded fingerprint
in the range, classified by the mapping valid on **its own** site-local day:

* **Verified** — a BambooHR team member; all of their ZKBioTime IDs valid that day are merged.
* **Unmapped** / **Mapping conflict** — the raw ZKBioTime ID only; never merged, never attributed.

Complete days are aggregated first; filters, sorting and paging apply afterwards. Σ punches per state
equals the Activity summary for the same range (`tests/test_v090_reconciliation.py`).

## Attendance review cases

A review case is an **administrative record**. It never changes `attendance_events` (biometric
records are immutable) or identity mappings, and a resolved case is **not** a verified duration.

### Four separate concepts

| Concept | Stored as | Shown as |
|---|---|---|
| Observed | facts snapshot (first / last fingerprint, Recorded Span, punch count, event hash, mapping basis) | Recorded evidence |
| Declared | `declared_departure_local` + `declaration_source` + evidence reference | Declared departure (administrative declaration) |
| Estimated | `estimated_minutes` + `estimate_basis` (server-computed) | Estimated interval — reviewed declaration, not a confirmed duration |
| Resolved | `outcome` (Justified / No further action / Not justified) + decision note | Resolved — duration not verified |

### Lifecycle (server-enforced)

```
(none) --open--> OPEN --submit--> SUBMITTED --resolve--> RESOLVED --reopen--> REOPENED --submit--> SUBMITTED
                                   SUBMITTED --submit (update)--> SUBMITTED
```

* Open needs a classification; submit needs a reason and an explanation (≥ 10 characters);
  resolve needs an outcome and a decision note (≥ 10); reopen needs a reason (≥ 10). A single
  fingerprint can be resolved **without** a declared departure (e.g. *Assigned off-site* +
  *No further action*).
* Anything else → **409** with the allowed actions. Every transition after open carries
  `expected_version`; the update is conditional on that version, so a concurrent decision gets 409
  and never silently overwrites another administrator.
* Open is idempotent on `(site, date, identity_key)`; a repeated transition writes nothing.
* Each transition writes exactly one append-only history row (actor, time, previous/new values,
  facts snapshot) plus a best-effort platform audit entry.
* Writes: `onsite.exceptions.manage` (On-site Admin only; no employee self-submission).
  Reads: `onsite.exceptions.read` (On-site User and Admin). `ONSITE_REVIEW_WRITES_ENABLED=false`
  freezes writes (503).

### Declared departure rules

* Site-local `HH:MM` on the case's date, converted with the site's IANA time zone; DST gaps and
  repeated times are rejected (422).
* Must be **at or after the latest** recorded fingerprint of the complete day and strictly after the
  first; a next-day declaration is rejected ("next-day declarations are not supported").
* Never defaulted (no office hours, never the last fingerprint), never counted as an event, never
  replaces Recorded Span. Estimate = declared departure − first recorded fingerprint.

## Identity changes, reassignments and corrections

* A case is keyed `P:<BHR ID>` (verified team member) or `C:<ZKBioTime ID>` (unmapped / conflict) and
  stores an immutable **identity snapshot** (kind, IDs, mapping IDs, mapping state — no names).
* Cases are **never re-keyed** and estimates **never move** between people. When a mapping is later
  created, corrected, closed or reassigned, the case stays on its original key and is flagged
  **"Needs reassessment — identity mapping changed"**. A verified team-member row lists earlier
  raw-ID cases for its IDs (`earlier_code_cases`) without attributing them.
* Conflict days are never attributed: a person's case never includes a conflicting ID's
  fingerprints.

## Staleness

Computed on read against the last snapshot (open / submit / resolve); nothing is recalculated:

* `FINGERPRINTS_CHANGED` — punch count, first/last time or the event hash changed;
* `IDENTITY_CHANGED` — the effective mapping set or state changed;
* `ESTIMATE_BASIS_INVALID` — a fingerprint is now later than the declared departure.

A stale SUBMITTED case must be resubmitted before it can be resolved; a stale RESOLVED case keeps
its decision and can be reopened.

## Reports

The **Daily Fingerprint Activity Summary** (`/activity/daily/export`) has two column groups —
**Recorded evidence** and **Administrative review** ("reviewed declarations — not biometric
records") — an optional Punch Detail and Case History, and a Summary that reports fingerprint counts
and case counts **separately, never summed**. Every On-site workbook states the report type, the
site time zone, the generation time in site time and UTC, and definitions.

## Migration and rollback

`0003_onsite_attendance_reviews` is additive (two new tables). The previous application image runs
unchanged against it and review rows survive an image rollback. Production rollback = previous
images with the schema retained; the downgrade is for CI only.
