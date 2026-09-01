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
| `POST /api/talent/requests` | `get_talent_scope`; unconditional `403` | retired — DijiTalentFlow is not a client intake portal (2026-09-01); no role holds `talent.requests.create` | no |
| `GET /api/talent/requests/{id}` | `get_talent_scope` | ✅ scoped `get_by_id` → 404 | no (404) |
| `POST /api/talent/requests/{id}/review` | `require_customer_success_scope` | ✅ scoped lookup | no (404) |
| `POST /api/talent/requests/{id}/stage` | `require_staff_scope` | ✅ `allowed_client_ids` → 404 + transition-validated | no (404) |
| `POST /api/talent/requests/{id}/ta-status` | `require_staff_scope` | ✅ `allowed_client_ids` → 404 | no (404) |
| `GET /api/talent/candidates` | `require_staff_scope` | global pool by design (note 2) | staff-only |
| `POST /api/talent/candidates` | `require_staff_scope` | global pool by design | staff-only |
| `GET /api/talent/candidates/{id}` | `require_staff_scope` | global pool by design | staff-only |
| `GET /api/talent/requests/{id}/candidates` | `get_talent_scope` | ✅ scoped request lookup; `ClientSafeCandidateOut` structurally omits score/notes/other-client rows | no (404) |
| `GET /api/talent/applications` | `require_staff_scope` | ✅ `list_for_scope(allowed_client_ids)` | no |
| `POST /api/talent/applications` | `require_staff_scope` | ✅ **now** `allowed_client_ids` → 404 (Shadow Validation 1) | no (404) |
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
| `GET /api/talent/postings` | `require_staff_scope` | staff-wide read of talent-api's local `RecruitmentPostingRef` projection (sourced from recruitment-api) | staff-only |
| `POST /api/talent/postings/{ref_id}/verify-mapping` | `require_staff_scope` | staff-only; `source=MANUAL` only | staff-only |
| `GET /api/talent/postings/client-visible` | `get_talent_scope` | ✅ **fail-closed** — inner join on `RecruitmentPostingRef` ↔ `PostingClientMapping.status == VERIFIED AND client_id == scope.client_id`, entirely local to talent-api (see `docs/platform/data-ownership.md` §4a) | no |
| `GET /api/talent/postings/{ref_id}` | `require_staff_scope` | staff-only | staff-only |
| `GET /api/talent/integrations/recruitment/freshness`, `/sync/latest`, `/sync/history`, `/sync/{run_id}` | `require_staff_scope` | staff-only | staff-only |
| `POST /api/talent/integrations/recruitment/sync` | `require_staff_scope` | staff-only; proxies to recruitment-api's `POST /api/recruitment/internal/sync`, 202 single-flight | staff-only |
| `POST /api/talent/internal/recruitment/reconcile` | `require_internal_service` (`X-Internal-Token`) | n/a — service-to-service (Container Apps Job target) | n/a |
| `GET /api/talent/summary` | **none, by design** | aggregate counts only (`open_requests`, `pending_requests`, `interviews_upcoming`) — no per-client data | n/a |
| `GET /health`, `/health/deep` | none | n/a | n/a |

**talent-api has no Lever/HubSpot webhook, no `/postings/sync`, and no
`/internal/clients-lite` route** — all three were removed by the
Architecture Completion Plan. Lever's webhook is
`POST /api/recruitment/webhooks/lever` on `recruitment-api`; HubSpot's is
`POST /api/commercial/webhooks/hubspot` on `commercial-api` (see note 3);
canonical client identity — and therefore client-name resolution — is
`platform-api`'s own `Client`/`ClientExternalId` tables, reached via
`GET /api/platform/internal/clients`, not a talent-api lookup. See
`docs/platform/data-ownership.md` for the full current ownership map.

## Notes

1. **`require_staff_scope` staff-wide endpoints — now all scoped.** This note
   previously flagged `/requests/{id}/stage`, `/requests/{id}/ta-status`, and
   `POST /applications` as resolving their target without `allowed_client_ids`,
   letting a *portfolio-restricted* staff user act on any client's request.
   `/stage` and `/ta-status` were already fixed by the time of this correction
   (both thread `allowed_client_ids` through `TalentRequestService`/
   `TalentRequestRepository._scoped`) — this doc had simply not been updated to
   match. `POST /applications` was still genuinely open — unlike the other
   Application mutation endpoints, it is not nested under
   `/requests/{request_id}/...`, so `talent_request_id` arrived straight from
   the JSON body with no URL-path id for the route layer to pre-scope; a
   portfolio-restricted staff user who knew a valid `candidate_id` +
   out-of-portfolio `talent_request_id` pair could create the link directly.
   Fixed (Shadow Validation 1) by validating `payload.talent_request_id`
   against `allowed_client_ids` in `ApplicationService.create_application`
   before creating the row, mirroring the existing `_get_or_raise` pattern
   used by the sibling mutation endpoints. The primary `TALENT_CLIENT`
   boundary was never affected by any of these three.
2. **Candidate pool is global by design** (CLAUDE.md §19 / Architecture v2 §3) —
   one master profile per person, reused across clients. Any staff user, including
   a portfolio-restricted one, sees the whole pool and each candidate's
   cross-client application list. `available_candidates` on the TA dashboard is
   therefore intentionally not portfolio-scoped.
3. **Webhooks live on `recruitment-api`/`commercial-api`, not talent-api**
   (moved in Waves B/F), and both now fail closed outside
   `app_env=development`: an unconfigured signing secret is a soft warning
   only in dev; anywhere else it's a `503`, not a silently-accepted
   unsigned payload. Lever's is real HMAC-SHA256 per Lever's own scheme;
   HubSpot's is a documented pre-shared-secret placeholder (not HubSpot's
   real v3 scheme — no live HubSpot credential exists yet to validate a
   real implementation against). See `docs/integrations/lever.md` and the
   webhook handlers in each service for the current state.

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
