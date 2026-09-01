# DijiTalentFlow — Route Authorization Review

Focused pre-DEV review (Wave 1). One row per `talent-api` route: its FastAPI
dependency, whether it applies the caller's client scope, and whether a raw id
in the path can reach another client's data.

**Model (unchanged):** authorization is resolved by `platform-api` at login and
carried in the JWT. `TalentScope` (`app/api/deps.py`) exposes `client_id`
(not-None only for `TALENT_CLIENT`), `client_ids` (staff *portfolio* — `None` =
ALL_CLIENTS, a list = restricted), and `permissions`. Tenant filtering happens
in the repository layer via `client_id` / `allowed_client_ids`. Cross-tenant
detail/mutation resolves to **404**, never 403 (existence is not leaked).

## Route table

| Route | Dependency | Client scope applied | Cross-client via path id? |
|---|---|---|---|
| `GET /api/talent/requests` | `get_talent_scope` | ✅ `list_for_scope(client_id, allowed_client_ids)`; `?client_id=` honoured only for staff | no |
| `POST /api/talent/requests` | `get_talent_scope` + inline `talent.requests.create` + `client_id is not None` | ✅ writes under caller's own `client_id` | no |
| `GET /api/talent/requests/{id}` | `get_talent_scope` | ✅ scoped `get_by_id` → 404 | no (404) |
| `POST /api/talent/requests/{id}/review` | `require_customer_success_scope` | ✅ scoped lookup | no (404) |
| `POST /api/talent/requests/{id}/stage` | `require_staff_scope` | ⚠️ staff-wide (see note 1) | staff-only |
| `POST /api/talent/requests/{id}/ta-status` | `require_staff_scope` | ⚠️ staff-wide (note 1) | staff-only |
| `GET /api/talent/candidates` | `require_staff_scope` | global pool by design (note 2) | staff-only |
| `POST /api/talent/candidates` | `require_staff_scope` | global pool by design | staff-only |
| `GET /api/talent/candidates/{id}` | `require_staff_scope` | global pool by design | staff-only |
| `GET /api/talent/requests/{id}/candidates` | `get_talent_scope` | ✅ scoped request lookup; `ClientSafeCandidateOut` structurally omits score/notes/other-client rows | no (404) |
| `GET /api/talent/applications` | `require_staff_scope` | ✅ `list_for_scope(allowed_client_ids)` | no |
| `POST /api/talent/applications` | `require_staff_scope` | ⚠️ staff-wide (note 1) | staff-only |
| `PATCH /api/talent/applications/{id}/stage` | `require_staff_scope` | ✅ **now** `allowed_client_ids` → 404 (Wave 1) + stage enum-validated | no (404) |
| `PATCH /api/talent/applications/{id}/status` | `require_staff_scope` | ✅ **now** `allowed_client_ids` → 404 (Wave 1) + status enum-validated | no (404) |
| `PATCH /api/talent/applications/{id}/score` | `require_staff_scope` | ✅ **now** `allowed_client_ids` → 404 (Wave 1) | no (404) |
| `PATCH /api/talent/applications/{id}/visibility` | `require_staff_scope` | ✅ **now** `allowed_client_ids` → 404 (Wave 1) | no (404) |
| `GET /api/talent/interviews` | `get_talent_scope` | ✅ `list_for_scope(client_id, allowed_client_ids)`; client gets client-safe DTO | no |
| `POST /api/talent/interviews` | `require_staff_scope` | ✅ **now** `allowed_client_ids` on the parent application → 404 (Wave 1) + type enum-validated | no (404) |
| `PATCH /api/talent/interviews/{id}/status` | `require_staff_scope` | ✅ **now** `allowed_client_ids` join → 404 (Wave 1) + status enum-validated | no (404) |
| `GET/POST /api/talent/requests/{id}/messages` | `get_talent_scope` | ✅ `_ensure_request_in_scope(client_id, allowed_client_ids)` | no (404) |
| `GET/POST /api/talent/requests/{id}/documents` | `get_talent_scope` | ✅ `_ensure_request_in_scope(client_id, allowed_client_ids)` | no (404) |
| `GET /api/talent/dashboard/client` | `get_talent_scope` + `talent.dashboard.read_own` + `client_id is not None` | ✅ own client only | no |
| `GET /api/talent/ta/dashboard` | `require_staff_scope` | ✅ **now** portfolio-scoped incl. `active_applications` / `interviews_scheduled` / `offers_in_progress` (Wave 1); `available_candidates` stays global (note 2) | n/a |
| `GET /api/talent/postings` | `require_staff_scope` | staff-wide read of the Lever read-model | staff-only |
| `POST /api/talent/postings/sync` | `require_staff_scope` | staff-only; read-only Lever pull | staff-only |
| `POST /api/talent/postings/{id}/verify-mapping` | `require_staff_scope` | staff-only; `source=MANUAL` only | staff-only |
| `GET /api/talent/postings/client-visible` | `get_talent_scope` | ✅ **fail-closed** — inner join on `PostingClientMapping.status == VERIFIED AND client_id == scope.client_id` | no |
| `GET /api/talent/postings/{id}` | `require_staff_scope` | staff-only | staff-only |
| `GET /api/talent/integrations/*`, `POST .../lever/sync-opportunities` | `require_staff_scope` | staff-only | staff-only |
| `POST /api/talent/webhooks/lever` | **none** (HMAC-SHA256 only if `LEVER_WEBHOOK_SIGNING_SECRET` set) | n/a; idempotent via `IntegrationEvent` | note 3 |
| `POST /api/talent/webhooks/hubspot` | **none, no signature check** | n/a; idempotent; drives no domain mutation | note 3 |
| `GET /api/talent/summary` | **none, by design** | aggregate counts only (`open_requests`, `pending_requests`, `interviews_upcoming`) — no per-client data | n/a |
| `GET /api/talent/internal/clients-lite` | `require_internal_service` (`X-Internal-Token`) | n/a — service-to-service | n/a |
| `GET /health` | none | n/a | n/a |

## Notes

1. **`require_staff_scope` staff-wide endpoints.** `/requests/{id}/stage`,
   `/requests/{id}/ta-status`, and `POST /applications` still resolve the target
   without `allowed_client_ids`, so a *portfolio-restricted* staff user can act
   on any client's request. Impact is lower than the application/interview
   mutation gap fixed in Wave 1 (those are the day-to-day grid actions), and
   `POST /applications` requires knowing a valid `candidate_id` + `talent_request_id`
   pair. **Tracked as P1** — same `allowed_client_ids` threading pattern; deferred
   only to keep Wave 1 tight. The primary `TALENT_CLIENT` boundary is unaffected.
2. **Candidate pool is global by design** (CLAUDE.md §19 / Architecture v2 §3) —
   one master profile per person, reused across clients. Any staff user, including
   a portfolio-restricted one, sees the whole pool and each candidate's
   cross-client application list. `available_candidates` on the TA dashboard is
   therefore intentionally not portfolio-scoped.
3. **Webhooks are unauthenticated by design** for the MVP. Lever verifies an HMAC
   only when a signing secret is configured (it is not, in dev); HubSpot does no
   verification. **Tracked as P1** — require the Lever HMAC and add a HubSpot
   signature check before registering production webhooks.

## Wave 1 changes summary

- `PATCH /applications/{id}/stage` contract fixed (`current_stage` → `stage`).
- `allowed_client_ids` threaded into every `application` + `interview` mutation
  and into the TA-dashboard aggregate counts.
- `InterviewRepository.get_by_id` gained an `allowed_client_ids` join.
- Enum validation added for application stage/status and interview status/type
  (unknown value → 400, not a 500 or silent bad state).
- Cross-service `client_id` guard: `AdminService` rejects a scope naming an
  unknown talent-api client (400), or 503 if talent-api is unreachable
  (fail-safe); `GET /health/deep` flags already-stored orphan scope ids.
