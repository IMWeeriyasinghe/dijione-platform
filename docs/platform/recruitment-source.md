# Recruitment Source (Lever) — DijiOne standard source-sync

**Status:** bounded module inside `talent-api`
(`apps/talent-api/app/recruitment_source/`). Promotion target: `apps/recruitment-api`
(Data Ownership Architecture v2 §10 — a lift, not a rewrite). This document
is the reference for the **DijiOne standard source-synchronization
lifecycle** every reusable source-data domain (People/Workforce,
Commercial/CRM, …) must follow — see the authoritative rules in the
`CLAUDE.md` section **"DIJIONE PLATFORM DATA OWNERSHIP AND SOURCE
SYNCHRONIZATION CONTRACT"**.

## What it owns

- The Lever client + adapters (`app/integrations/lever/*`), the two
  reconciliation services (`lever_posting_service`,
  `lever_contact_application_sync_service`), the stage/archive mappers, and
  the Lever-sourced read-model tables (`postings`, `posting_applications`,
  `candidates` where `source=LEVER`).
- `recruitment_sync_runs` — durable sync-run state (`run_id`, provider,
  `trigger_type`, requesting app/user, timestamps, status, counts,
  correlation id, safe error summary). **No secrets, no raw PII.**

**Not owned here:** `PostingClientMapping` (TalentFlow trust/business
decision — `UNMAPPED`/`VERIFIED`; client exposure fails closed, never
inferred from Lever tags/title/team/text), `TalentRequest`, `Application`,
messages, documents, client-safe DTOs.

**Lever is GET-only** (CLAUDE.md §60). `test_live_lever_client_safety.py`
plus `test_no_direct_lever_dependency.py` guard this.

## Sync lifecycle

| Concern | Implementation |
|---|---|
| **Scheduled reconciliation** | Every 6 h, via an external replica-safe caller: `POST /api/talent/internal/recruitment/scheduled-sync` (`X-Internal-Token`). Azure = a Container Apps scheduled Job (`deploy/` — prepared, not created). Local = cron / `curl` / a script. **Not** an in-process timer per replica. |
| **Ad-hoc sync** | `POST /api/talent/integrations/recruitment/sync` (staff, `require_staff_scope`). Browser → `talent-web` → `talent-api` → this module. Never browser → source directly. |
| **Async** | Ad-hoc returns **`202 Accepted`** `{run_id, status, started}`; the run executes in a FastAPI background task with its own DB session. The HTTP request is never held open. |
| **Single-flight** | `request_sync` returns any already-`QUEUED`/`RUNNING` run instead of starting a second full reconciliation (`started: false`). No provider thundering herd. |
| **Idempotent** | Reconciliation = insert new / update changed / keep stable IDs. Repeated runs over unchanged Lever data are harmless. A failed run leaves the previous read model intact (no wipe). |
| **Retry / rate limits** | The existing `LiveLeverClient` retry (429 backoff, transient 5xx) is preserved unchanged. |
| **Freshness** | `GET /api/talent/integrations/recruitment/freshness` → `last_successful_sync_at` + latest-run summary. |
| **Frontend** | `RecruitmentSyncStatus` on the TA Operations Dashboard — freshness line, authorized "Sync now", indeterminate spinner (no faked %), bounded 3 s polling with unmount cleanup, dashboard refetch on completion. Backend-enforced auth. |
| **Notifications** | SCHEDULED success → silent freshness update. SCHEDULED failure → `TA_MANAGER` operational warning. AD_HOC success → lightweight confirmation to the requester. AD_HOC failure → clear error to the requester. Uses `NotificationService` (best-effort). |
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

- **Lever unavailable** → run `FAILED`, prior read model kept, freshness goes
  stale.
- **This module errors** → TalentFlow core workflow unaffected; the sync
  widget degrades; no TalentFlow DB corruption.
- **`platform-api` unavailable** → sync still succeeds; audit/notification
  writes are best-effort (verified live).

## Mock mode

`INTEGRATIONS_MODE=mock` (default) drives the whole lifecycle against
`MockLeverClient` — CI, local dev, and the first shared DEV run end-to-end
with **no Lever credentials**.

## Remaining (post-demo R-work)

Physical lift to `apps/recruitment-api` + its own Postgres DB; re-key
`PostingClientMapping` to `(provider=LEVER, external_posting_id)`; the
Container Apps scheduled Job; a `talent-api → recruitment-api` HTTP client
replacing the in-process module call.
