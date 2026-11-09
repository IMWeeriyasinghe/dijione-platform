# Recruitment Source (Lever) — DijiOne standard source-sync

**Status:** an independently deployable service, `apps/recruitment-api`
(port 8005, `recruitment_dev`) — physically extracted from `talent-api` in
Architecture Completion Plan Wave B. `talent-api` consumes it exclusively
over HTTP via `RecruitmentSourceClient` (Wave C); it holds no Lever
credential and imports nothing from `app.integrations.lever`
(`tests/test_no_direct_lever_dependency.py` guards an empty allowlist).
This document is the reference for the **DijiOne standard
source-synchronization lifecycle** every reusable source-data domain
(`recruitment-api`, `people-api`, and `commercial-api` when built) follows
— see the authoritative rules in the `CLAUDE.md` section **"DIJIONE
PLATFORM DATA OWNERSHIP AND SOURCE SYNCHRONIZATION CONTRACT"** and the
People/Workforce equivalent in `docs/platform/data-ownership.md` §4b.

## What it owns

- The Lever client + adapters (`app/integrations/lever/*`), the
  reconciliation services (`lever_posting_service`,
  `lever_candidacy_sync_service`), the stage/archive mappers, and the
  Lever-sourced read-model tables: `postings`, `recruitment_candidates`,
  `recruitment_candidacies`, `external_mappings`, `integration_events`.
- `sync_runs` — durable sync-run state (`run_id`, provider, `trigger_type`,
  requesting app/user, timestamps, status, counts, correlation id, safe
  error summary). **No secrets, no raw PII.**

**Not owned here:** `PostingClientMapping` (TalentFlow's trust/business
decision — `UNMAPPED`/`VERIFIED`; client exposure fails closed, never
inferred from Lever tags/title/team/text — lives in `talent_dev`),
`RecruitmentPostingRef` (talent-api's thin local projection for the
fail-closed authorization join — `docs/platform/data-ownership.md` §4a),
`TalentRequest`, `Application`, messages, documents, client-safe DTOs.

**Lever is GET-only** (CLAUDE.md §60). `test_lever_client_safety.py` plus
`test_no_direct_lever_dependency.py` (in `talent-api`) guard this.

## Reconcile outcomes

`POST /api/talent/internal/recruitment/reconcile` runs synchronously, so the
`curl -f` in `talent-reconcile-job` reports the real result.

**Why this exists.** Until November 2026 every scheduled reconcile failed
silently with `ReadTimeout` in every hosted environment. `recruitment-api`
scales to zero about 5 minutes after the `:00` sync, so the `:15` reconcile
always found it cold. Its start took 7-47 s against a 5 s timeout. The route
returned 202 before doing the work, so Azure recorded success. It was not an
overlap with the sync, and moving the schedule would not fix it.

| Outcome | HTTP | Azure job | Data | Meaning |
|---|---|---|---|---|
| `SUCCEEDED` | 200 | Succeeded | Committed | Postings and candidacies fully read |
| `FAILED` / `candidacies_unavailable` | 503 | Failed, retried once | Rolled back, including mapping changes | Any posting's read failed or could not be proven complete |
| `PARTIAL` / `no_postings` | 503 | Failed, retried once | Nothing to change | Investigate if the retry also reports it |
| `SKIPPED` / `already_running` | 409 | Failed | Unchanged | Another replica or run holds the lock |
| `FAILED` | 503 | Failed, retried once | Rolled back | Source unavailable, error, or over budget |

- `fully_refreshed` is true only for `SUCCEEDED`. Every other outcome logs a
  `recruitment reconcile outcome=...` warning; `curl -f` hides failure bodies.
- **Timeouts:** 90 s per batch call, 5 s for browser-facing calls. The run stops
  at 220 s and rolls back, inside the 240 s Container Apps request limit. Two
  attempts fit within the job's 900 s limit. The 220 s check is cooperative: if
  Azure cuts a longer request off, the job shows Failed and the final check
  before commit still rolls the run back. PostgreSQL statements stop at 60 s and
  lock waits at 15 s.
- **Single-flight:** a PostgreSQL transaction advisory lock covers all replicas
  and is released on commit, rollback or lost connection.
- **Transaction:** one database transaction, committed last, and safe to re-run.
- **Side effects:** audit and notification calls are queued and sent only after
  commit, after the response, for at most 200 s. A rolled-back run sends none.
  Delivery stays best-effort; losses are logged as `side effects undelivered`.
- **Incomplete data:** a `PARTIAL` commit never deletes or withdraws anything,
  and new applications stay unshared until TA shares them. The freshness panel
  reports the Lever sync, not this reconcile, so check the job status as well.

## Completeness

- `OPPORTUNITY_SYNC_LIMIT` (200) caps the general read of Lever opportunities
  and has no continuation, so older opportunities are not refreshed by it.
- Every posting with a DTC tag is therefore also read in full through Lever's
  `posting_id` filter. Those are the only postings TalentFlow can promote.
- `talent-api` reads candidacies one verified posting at a time, so its
  500-row limit applies per posting.

## Sync lifecycle

| Concern | Implementation |
|---|---|
| **Scheduled reconciliation** | Every 6 h, via an external replica-safe caller: `POST /api/recruitment/internal/scheduled-sync` (`X-Internal-Token`). Azure = the `recruitment-sync-job` Container Apps Job (`deploy/` — prepared, not created). Local = cron / `curl` / a script. **Not** an in-process timer per replica. `talent-reconcile-job` runs 15 min later to refresh `talent-api`'s posting projection + DTC trust reconciliation; see "Reconcile outcomes" below. |
| **Ad-hoc sync** | `POST /api/talent/integrations/recruitment/sync` (staff, `require_staff_scope`) proxies to `POST /api/recruitment/internal/sync` on this service. Browser → `talent-web` → `talent-api` → `recruitment-api`. Never browser → source directly. |
| **Async** | Ad-hoc returns **`202 Accepted`** `{run_id, status, started}`; the run executes in a FastAPI background task with its own DB session. The HTTP request is never held open. |
| **Single-flight** | `request_sync` returns any already-`QUEUED`/`RUNNING` run instead of starting a second full reconciliation (`started: false`). No provider thundering herd. |
| **Idempotent** | Reconciliation = insert new / update changed / keep stable IDs. Repeated runs over unchanged Lever data are harmless. A failed run leaves the previous read model intact (no wipe). |
| **Retry / rate limits** | `LiveLeverClient` retry (429 backoff, transient 5xx). |
| **Freshness** | `GET /api/recruitment/freshness` (proxied via `GET /api/talent/integrations/recruitment/freshness`) → `last_successful_sync_at` + latest-run summary. |
| **Frontend** | `RecruitmentSyncStatus` on the TA Operations Dashboard — freshness line, authorized "Sync now", indeterminate spinner (no faked %), bounded polling with unmount cleanup, dashboard refetch on completion. Backend-enforced auth. |
| **Notifications** | SCHEDULED success → silent freshness update. SCHEDULED failure → `TA_MANAGER` operational warning. AD_HOC success → lightweight confirmation to the requester. AD_HOC failure → clear error to the requester. Best-effort via `PlatformClient`. |
| **Audit** | One `recruitment.sync_requested` platform audit event per authorized ad-hoc request — not one per synced record. |

## DTC client-tag resolution (governed Lever posting tag)

The TA business maintains a dedicated Lever posting tag **`DTC - <Client
Name>`** naming the DijiTalentFlow client for that posting. This is a
governed identifier, not arbitrary text inference.

| Layer | Owner | Component |
|---|---|---|
| Parse the tag (provider fact) | Recruitment Source | `app/recruitment_source/dtc.py` — pure `parse_dtc(tags) -> NO_TAG / OK(name,raw) / MALFORMED / MULTIPLE`. Case-insensitive `DTC`, 0+ spaces around `-`, internal name text preserved, non-DTC tags ignored, **no fuzzy matching** |
| Resolve + decide trust | DijiTalentFlow | `app/services/posting_client_mapping_reconciler.py` — exact `Client.name` match → reconcile `PostingClientMapping`; runs inside `SyncService.execute_run` (scheduled + ad-hoc), in the sync transaction |

**Fail-closed policy** (anything but a clean resolution → not client-visible):

| Case | Result | `resolution_status` |
|---|---|---|
| 1 tag, 1 exact `Client` match, no MANUAL conflict | `VERIFIED`, `source=LEVER_DTC_TAG` | `RESOLVED` |
| 1 tag, no `Client` match | stays `UNMAPPED` (tag recorded) — **no `Client` auto-created** | `UNKNOWN_CLIENT_IDENTIFIER` |
| >1 DTC tag | stays `UNMAPPED` | `AMBIGUOUS_MULTIPLE_TAGS` |
| malformed (`DTC`, `DTC -`, …) | stays `UNMAPPED` | `MALFORMED_TAG` |
| no DTC tag | stays `UNMAPPED` | `NO_DTC_TAG` |
| tag removed / broken on a DTC-`VERIFIED` mapping | **revert → `UNMAPPED`** (visibility lost) | reason recorded |
| tag changed A→B (both resolve, DTC-`VERIFIED`) | repoint `client_id` | `RESOLVED` |
| existing `source=MANUAL` `VERIFIED` mapping agrees | untouched | `RESOLVED` |
| existing `source=MANUAL` `VERIFIED` mapping conflicts | **kept — never overwritten** + `TA_MANAGER` notification | `CONFLICT_MANUAL_OVERRIDE` |
| existing `REJECTED` | never un-rejected | — |

The fail-closed visibility query (`list_verified_for_client`: `status==VERIFIED
AND client_id==<own>`) is **unchanged** — the tag is a *source that writes*
that state, alongside the staff `verify-mapping` (`source=MANUAL`) action.
Every state transition is audited (one event per transition, never per row).
Staff see it on `talent-web` `/postings`. **HubSpot is not required for this.**

## Failure isolation

- **Lever unavailable** → the run is `FAILED`, `recruitment-api` keeps its
  prior read model, freshness goes stale.
- **`recruitment-api` itself is down** → `talent-api`'s client-visibility
  authorization decision keeps working from its local
  `RecruitmentPostingRef` projection — fail-closed, not fail-unavailable;
  see `docs/platform/data-ownership.md` §4a for the full contract and
  `apps/talent-api/tests/test_recruitment_source_consumer.py` for the
  failure-injection tests. TalentFlow's core workflow (requests,
  applications, interviews, messages, documents) is entirely unaffected —
  none of it depends on `recruitment-api`.
- **`platform-api` unavailable** → sync still succeeds; audit/notification
  writes are best-effort (verified live).

## Mock mode

`INTEGRATIONS_MODE=mock` (default) drives the whole lifecycle against
`MockLeverClient` — CI, local dev, and the first shared DEV run end-to-end
with **no Lever credentials**. `INTEGRATIONS_MODE=live` was verified once,
GET-only, against the real Lever tenant (647 postings synced, zero writes)
to confirm the two governed DTC test postings resolve correctly — see
`docs/platform/data-ownership.md` and the Architecture Completion Plan's
final report for the result.

## Client-posting completeness

Each `DTC` posting is read and committed on its own, with a checkpoint. The next
run starts from the least recently attempted posting, so an interrupted run
resumes and a failing posting cannot hold back the others. A run is `PARTIAL`
while any posting failed or was deferred.

`/freshness` returns `source_snapshot.state`. `COMPLETE` requires every client
posting to have been read within 24 hours and the latest finished run not to
have failed. Talent reconcile holds, with no writes, in any other state.

`recruitment-sync-job` runs `scripts/run_scheduled_sync.py`, which polls until
the run finishes. The polling keeps the replica up under the background task.
