# Lever Integration — Live Discovery & Reference

**Status: extracted, live-verified, GET-only.** This document was
substantially rewritten in Architecture Completion Plan Wave G — the prior
version described a pre-extraction, mock-only, "not built yet" state that
no longer matches the codebase; see `docs/platform/recruitment-source.md`
for the full sync-lifecycle reference this document doesn't repeat.

## Ownership

Lever is Dijital Team's Applicant Tracking System and recruitment source of
truth (CLAUDE.md §26): candidates, opportunities, requisitions, postings,
pipeline stages, interviews, feedback, offers. `apps/recruitment-api` is the
**sole** DijiOne owner of the Lever integration (CLAUDE.md rule 3) —
`talent-api` holds no Lever credential and imports nothing from
`app.integrations.lever` (`talent-api/tests/test_no_direct_lever_dependency.py`
guards an empty allowlist).

```text
apps/recruitment-api/app/integrations/lever/
├── client.py         # LeverClient — abstract interface (GET/list/get only)
├── live_client.py     # LiveLeverClient — real HTTP calls, no write method exists
├── mock_client.py      # MockLeverClient — realistic in-memory fixture data
├── mapper.py           # LEVER_STAGE_MAP + archive-outcome mapping (below)
└── schemas.py           # Provider-shaped DTOs (never returned to a frontend)

apps/recruitment-api/app/recruitment_source/dtc.py   # DTC posting-tag parser
```

`app/integrations/factory.py: get_lever_client()` returns `MockLeverClient`
whenever `INTEGRATIONS_MODE=mock` (the default everywhere except the one
verification run below) or no `LEVER_API_KEY` is configured. `LiveLeverClient`
exposes **no write method at all** — the abstract interface is entirely
`list_*`/`get_*` — and a static safety test
(`tests/test_lever_client_safety.py`) asserts the source contains no
`.post(/.put(/.patch(/.delete(` call and that no method name implies a
write. CLAUDE.md §60's READ-ONLY LEVER contract remains in force
unconditionally.

## Live verification performed (GET-only, real tenant)

A one-time, read-only sync run was executed against the real Dijital Team
Lever tenant to confirm connectivity, the posting sync path, and the DTC
tag resolution end-to-end: **647 postings synced, zero writes.** The two
governed DTC test postings resolved correctly:

| Posting | Lever tag | Parsed `client_name` |
|---|---|---|
| "AI Solutions Engineer" | `DTC - Agent Maestro` | `Agent Maestro` |
| "Technical Delivery Lead" | `DTC - Crofti` | `Crofti` |

No candidate/opportunity/interview/offer data was pulled as part of this
verification pass — it exercised the posting sync + DTC parser only, the
minimum needed to confirm the client-mapping mechanism against real data.
The API key used was copied, run, and then removed from local config
without ever being printed, logged, or committed; `INTEGRATIONS_MODE` is
`mock` in every checked-in `.env.example` and in CI.

## Stage mapping (confirmed against the real 14-stage pipeline)

`LEVER_STAGE_MAP` (`app/integrations/lever/mapper.py`) was rewritten
against the real Dijital Team Lever pipeline (not a guess) during the live
posting/opportunity discovery. Several entries are explicitly marked
**PROPOSED DEFAULT — needs business confirmation** in the code and below;
treat those as the current best mapping, not a settled business decision:

| Lever stage | Canonical stage | Notes |
|---|---|---|
| New lead / Reached out / Responded / New applicant | `SOURCING` | Intake, not yet screened |
| Recruiter Phone Screen | `SCREENING` | |
| SparkHire Assessment Stage | `SCREENING` | Spark Hire itself is **not integrated** (CLAUDE.md §60/§62 — P3) |
| TestGorilla Assessment | `SCREENING` | TestGorilla itself is **not integrated** |
| SME Interview | `SCREENING` | ⚠️ proposed default — an internal subject-matter-expert vetting step, not yet client-facing |
| Predictive Talent Assessment | `SCREENING` | |
| Presented to Customer | `CLIENT_REVIEW` | |
| Client Interview | `INTERVIEWS` | |
| Reference check | `OFFER` | ⚠️ proposed default — sits immediately before Offer in Lever's pipeline order (rank 260.5 vs 261) |
| Offer | `OFFER` | |
| Offer Declined | `OFFER` | ⚠️ proposed default — DijiOne has no "declined" canonical stage; a negative outcome belongs on `Application.status`, set by whatever consumes this, not this mapper |

**"Hired" is confirmed NOT a Lever pipeline stage** — it is an Archive
Reason. **`DEPLOYED` has no Lever equivalent at all** and must never be
expected from Lever data; it is exclusively DijiOne-owned, post-hire state
set by DijiTalentFlow's own workflow. An unrecognized stage text falls back
to `SOURCING` rather than raising, so a mapping gap degrades gracefully
instead of breaking sync.

## Archive reasons (confirmed by live tenant discovery)

"Hired" is the only Lever archive reason with `type: "hired"`; every other
configured reason is `type: "non-hired"`. Only "Withdrew" gets its own
`ApplicationStatus` (`WITHDRAWN`) — every other non-hired reason collapses
to `REJECTED` for the canonical field, with the raw Lever text preserved
separately (on the recruitment-api candidacy record, surfaced to staff) for
diagnostics — never silently discarded.

## Interviews

Live discovery found this tenant's structured Lever interview records
**empty** — real interviews are tracked elsewhere in the current TA
process, not in Lever's interview object for this tenant. `LiveLeverClient`
still implements the interview-listing method for completeness, but
nothing in `recruitment-api` or `talent-api` currently depends on it
returning data. **Open business decision** (unchanged since the original
audit): where interviews should be sourced from long-term is still
undecided — DijiTalentFlow's own `Interview` entity (staff-entered) remains
the working source of truth in the meantime.

## Client identity — the DTC governed tag (not HubSpot)

Lever has no native client/customer entity, so a `Posting → Client` link
cannot be derived from Lever data alone. The approved mechanism is the
governed posting tag **`DTC - <Client Name>`**, parsed as a Recruitment
Source provider fact (`app/recruitment_source/dtc.py`'s `parse_dtc`) and
resolved to trust by TalentFlow (`posting_client_mapping_reconciler.py`) —
exact match, fail-closed, never auto-creates a `Client`, never overwrites a
MANUAL mapping. Full rules: CLAUDE.md rule 4a,
`docs/platform/recruitment-source.md` "DTC client-tag resolution". This
supersedes the original audit's HubSpot-gated `Posting → Client` blocker —
HubSpot remains reserved for future commercial/CRM data only (rule 2a/3),
never for this link.

## Sync lifecycle

See `docs/platform/recruitment-source.md` for the full standard
source-synchronization lifecycle (scheduled/ad-hoc/async/single-flight/
idempotent/freshness/notifications) — not repeated here to avoid drift
between two copies of the same reference.

### Local dev: do not run mock mode against a live-synced database

`INTEGRATIONS_MODE` selects the data *source* (real Lever GET vs.
`MockLeverClient` fixtures) but **not** the database — both modes write to
the same `recruitment.db`. If you run a live GET-only discovery sync and
then flip `INTEGRATIONS_MODE` back to `mock` (the correct resting state
between controlled live sessions) and a sync fires, the 3 mock fixture
postings (`post-senior-ppd`, `post-senior-py`, `post-cloud-arch`) get
mixed in among the real rows and later surface as phantom "demo" postings
on DijiTalentFlow's Recruitment Postings screen.

`LeverPostingSyncService.sync_postings()` now **refuses** a mock-mode
sync when the database already holds any non-fixture posting
(`MockSyncAgainstRealDataError`), and the run is marked `FAILED` with a
clear summary rather than contaminating the data. For isolated mock
testing, point `DATABASE_URL` at a disposable file
(`DATABASE_URL=sqlite:///./scratch-mock.db`), or just run the test suite,
which already uses its own DB.

## Webhook handling

`POST /api/recruitment/webhooks/lever` — HMAC-verified when a signing
secret is configured (unset in dev; a misconfigured/absent secret is a
known, documented gap, not a silent one — see
`docs/platform/data-ownership.md` §2). No webhook has been registered
against a reachable URL to date; this path is exercised by tests only.

## Open items (unchanged from the original audit unless noted)

- Committed, reproducible run evidence beyond this document (a full
  structured discovery log) has not been produced — this doc is that
  evidence for the DTC-relevant path; a broader discovery pass (stages,
  archive reasons, custom fields — much of which is now folded into
  `mapper.py`'s own comments above) has effectively happened, but was not
  captured as a separate raw-data artifact.
- The "proposed default" stage mappings above still need TA/CS sign-off
  against the real pipeline.
- The interview data-source decision (Lever vs. DijiTalentFlow-native)
  remains open.
- No Lever webhook is registered against any reachable environment yet —
  Wave K (Azure DEV) territory once a stable public/internal URL exists.
