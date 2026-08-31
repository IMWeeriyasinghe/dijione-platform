# DijiOne Data Ownership & Service Dependency Contracts

Authoritative "who owns what, who calls whom, and what happens when the
callee is down" reference for the whole platform. Companion to
`docs/platform/service-architecture.md` (the service map) and
`docs/platform/service-contracts.md` (the API surface). Supersedes any
earlier text describing Lever/BambooHR as owned inside `talent-api`/
`birthday-api`, or canonical Client identity as a `talent-api` table.

## 1. Canonical Client / Organisation identity

**`platform-api` permanently owns identity.** One migration, no interim
registry (Architecture Completion Plan §6.1).

- `Client` (`platform_dev`): `id`, `public_id` (stable, non-sequential —
  the value every other service stores as `client_ref` / `client_public_id`
  / `platform_client_id`), `name`, `status`
  (`PROSPECT`/`ACTIVE`/`INACTIVE`/`ARCHIVED`), timestamps.
- `ClientExternalId` (`platform_dev`): `(provider, external_id) → client_id`
  crosswalk populated by source domains (today: `talent-api`'s legacy
  integer ids, for backward-compatible reseeding).
- `talent-api.clients` is a **TalentFlow-owned extension** keyed by
  `platform_client_id` — TA account manager, portfolio groupings. It does
  not duplicate identity; `talent_requests`, `posting_client_mappings`, and
  interview/scope references key on the platform identity.
- `UserModuleClientScope.client_ref` / `GroupModuleClientScope.client_ref`
  (`platform_dev`) carry the `Client.public_id` directly — the
  authorization-critical read never depends on another service being up.
  The legacy bare `client_id` integer (historically assumed to equal
  `talent-api.clients.id` by seed-insertion order) is kept alongside for
  backward compatibility only; new code reads `client_ref`.
- **Commercial/CRM's role, permanently:** a source domain that supplies
  commercial *facts about* clients (industry, account owner, deal context)
  in `commercial_dev`, keyed by `client.public_id`, and may **propose** new
  organisations for a platform-admin to confirm. It never owns the identity
  row — HubSpot holds companies that are not DijiOne clients, and DijiOne
  has clients not yet in HubSpot.

## 2. One provider, one owner

| Provider | Owner | Access mode | Notes |
|---|---|---|---|
| Lever | `recruitment-api` | **GET-only**, enforced by `LiveLeverClient`'s construction + `test_lever_client_safety.py` | Sole Lever credential in the platform. `talent-api` has zero Lever imports (`tests/test_no_direct_lever_dependency.py` guards an empty allowlist). |
| BambooHR | `people-api` | GET (a "custom report" read) | Sole BambooHR credential. `birthday-api` has zero BambooHR imports (`tests/test_no_direct_bamboohr_dependency.py`). |
| HubSpot | `commercial-api` (skeleton; no live client yet) | none yet | Stub client + unauthenticated `/webhooks/hubspot` relocated here from `talent-api`; no credential requested. |
| Microsoft Entra ID / Graph (auth) | `platform-api` | OIDC Auth Code + PKCE, JWKS | Identity boundary. |
| Microsoft Graph (email) | `birthday-api` | client-credentials, mock by default | Independent of the identity Graph usage — see §6. |

A test/static guard exists for every "one owner" rule above; a new direct
import of a provider client outside its owning service is a build-breaking
regression, not a style preference.

## 3. Data ownership by table (representative, not exhaustive)

| Service | DB | Owns |
|---|---|---|
| `platform-api` | `platform_dev` | `users`, `user_module_roles`, `user_module_client_scopes`, `roles`, `permissions`, `role_permissions`, `application_modules`, `audit_logs`, `notifications`, `access_groups`, `user_group_memberships`, `group_module_roles`, `group_module_client_scopes`, `clients`, `client_external_ids` |
| `talent-api` | `talent_dev` | `clients` (TalentFlow extension, keyed on `platform_client_id`), `talent_requests`, `candidates`, `applications`, `interviews`, `messages`, `documents`, `posting_client_mappings` (trust decision), `recruitment_posting_refs` (thin local projection — §4) |
| `recruitment-api` | `recruitment_dev` | `postings`, `recruitment_candidates`, `recruitment_candidacies`, `external_mappings` (LEVER), `integration_events` (LEVER), `sync_runs` |
| `people-api` | `people_dev` | `employees`, `people_sync_runs` |
| `birthday-api` | `birthday_dev` | `birthday_orders` (incl. order-time employee snapshot columns), `suppliers`, `supplier_locations`, `supplier_catalogue_items`, `supplier_users`, `order_issues`, `scan_runs`, `detection_config` |
| `commercial-api` | `commercial_dev` (later) | `integration_events` (HubSpot) today; a commercial-facts read model when HubSpot access lands |
| `admin-api` | none | zero-DB BFF |
| `spark-api` | none yet | skeleton |

## 4. Degraded-mode design — two different patterns, deliberately

The platform has **two** distinct read-dependency shapes on a source
domain, and each gets the pattern suited to it. This asymmetry is
intentional, not an inconsistency:

### 4a. Authorization-critical read → thin local projection, fail-closed

`talent-api`'s client-visibility decision (`PostingClientMapping.status ==
VERIFIED AND client_ref == caller's own client`) must stay **available**
even if `recruitment-api` is down, and must never widen access while
degraded. So `talent-api` keeps a **thin local projection**
(`RecruitmentPostingRef`: `provider`, `external_id`, `title`, `state`,
`location`, `archived`, `dtc_status`, `dtc_client_name`, `source_synced_at`)
refreshed opportunistically from `recruitment-api`'s sync/reconcile calls.

`PostingRepository.list_verified_for_client` inner-joins
`RecruitmentPostingRef` ↔ `PostingClientMapping` on `(provider,
external_id)` — **both tables are local to `talent_dev`** — so the
authorization decision never depends on `recruitment-api` being reachable.
`recruitment-api` DOWN → the client workspace still loads, VERIFIED
postings render from the local projection with a "last synced at …"
timestamp, no cross-client leakage, no widened access, no 500. Verified by
`apps/talent-api/tests/test_recruitment_source_consumer.py`'s
failure-injection tests.

This is **not** a second canonical Lever store: it carries none of the
fields `recruitment-api` itself owns for diagnostic/sourcing purposes
(owner ids, raw tag lists, candidacy data), only what the authorization
join and the client-facing list view need.

### 4b. Workflow-trigger read → defer and self-heal, no mirror at all

`birthday-api`'s daily detection scan is a **trigger**, not an
authorization decision — creating an order a day late during a genuine
`people-api` outage is an acceptable, self-correcting degradation; showing
the wrong person's data or leaking access is not on the table either way.
So `birthday-api` keeps **no employee mirror or projection table** — the
architecture's "no cross-service DB access, durable employee state lives
only in `people_dev`" rule holds with zero exception here.

Instead, `run_daily_scan` wraps its initial `EmployeeSourceClient` call:

```python
try:
    active_employees = employee_client.list_active_employees()
except EmployeeSourceUnavailableError:
    scan_run.status = ScanRunStatus.DEFERRED_SOURCE_UNAVAILABLE.value
    scan_run.finished_at = datetime.now(UTC)
    db.commit()
    return {"status": "DEFERRED_SOURCE_UNAVAILABLE", "orders_created": 0, ...}
```

No orders are created, no partial/invalid state is written. The **next**
scan (daily) recomputes the same **forward occurrence window**
(intentionally wider than any realistic outage, and never narrower than the
supplier lead time) and creates the correct orders — the scan's
`UniqueConstraint(employee_id, birthday_year)` idempotency guarantees a
deferred-then-recovered window produces no duplicates even if a partial
scan happened before the outage.

**In-flight `BirthdayOrder` rows are completely unaffected** by a
`people-api` outage — CS approval, address verification, supplier dispatch,
delivery tracking, and outbound email all read the employee facts
**snapshotted onto `BirthdayOrder` at detection time**, never a live
lookup. The staff directory view
(`GET /api/birthday/employees/upcoming-birthdays`) shows a "temporarily
unavailable" state — informational only, not workflow-critical.

| | 4a. `talent-api` ← `recruitment-api` | 4b. `birthday-api` ← `people-api` |
|---|---|---|
| Read is | an **authorization** decision | a **workflow trigger** |
| Must stay available while degraded? | Yes — fail-closed, not fail-unavailable | No — safe to defer |
| Local copy of source data? | Yes — thin projection, refreshed opportunistically | **No** — zero employee table in `birthday_dev` |
| On source-down | Serves from local projection, shows staleness | Defers, records `DEFERRED_SOURCE_UNAVAILABLE`, creates nothing |
| Recovery | Next successful sync refreshes the projection | Next scan's forward window + idempotency self-heals, no duplicates |
| In-flight work affected? | N/A (this is a read path, not a workflow) | No — snapshots on `BirthdayOrder` never touch live data |

## 5. Provenance columns vs live joins

`Application.lever_opportunity_id` / `lever_archive_reason` /
`lever_offer_status` and `BirthdayOrder`'s employee/address columns are
**operational snapshots on application-owned workflow state**, not a
second read model of provider data — they record what was true when the
row was written or last synced, exactly like an audit log. After Waves C/E
they are written from `recruitment-api`/`people-api` DTOs over HTTP, never
a live provider call from the application service.

## 6. Per-dependency contract table

Every internal HTTP dependency in the platform, with its failure posture.
`timeout` is the calling service's client-side budget; `auth` is always
`X-Internal-Token` (service calls) or a forwarded user bearer (BFF calls) —
see `docs/platform/service-contracts.md` "Service-to-service trust
boundaries".

| Caller → Callee | Contract | Timeout | Failure behaviour | Auth | Versioning |
|---|---|---|---|---|---|
| `talent-api` → `recruitment-api` (postings/candidacies) | `GET /api/recruitment/postings`, `/postings/{external_id}`, `/candidacies` | 5s | Serve last-good local projection (§4a); "as of &lt;ts&gt;"; authz unaffected | `X-Internal-Token` | Additive-only DTO fields; a breaking change needs a new `talent-api` release in lockstep |
| `talent-api` → `recruitment-api` (ad-hoc sync) | `POST /api/recruitment/internal/sync` → `202 {run_id}` | 5s | Soft error to the requester; freshness unchanged | `X-Internal-Token` | — |
| Job → `recruitment-api` | `POST /api/recruitment/internal/scheduled-sync` → `202` | n/a | Run marked `FAILED`; prior read model kept; freshness stale; `TA_MANAGER` warned | `X-Internal-Token` | — |
| `birthday-api` → `people-api` (employees) | `GET /api/people/employees`, `/employees/{bamboohr_id}` | 5s | Detection scan defers (§4b); directory view shows "unavailable" | `X-Internal-Token` | Additive-only |
| Job → `people-api` | `POST /api/people/internal/scheduled-sync` → `202` | n/a | Run marked `FAILED`; prior read model kept | `X-Internal-Token` | — |
| Job → `birthday-api` | `POST /api/birthday/internal/run-daily-scan` → `202` | n/a | See §4b | `X-Internal-Token` | — |
| `talent-api`/`birthday-api`/`recruitment-api`/`people-api` → `platform-api` (audit/notify) | `POST /api/platform/internal/{audit-events,notifications,notifications/broadcast}` | 2s | Swallowed, logged, `return False` — best-effort, never fails the caller's business operation | `X-Internal-Token` | — |
| `talent-api`/`admin-api` → `platform-api` (client directory) | `GET /api/platform/internal/clients` → `[{public_id, name, status}]` | 3s | Cache/last-good display names; a stale name never affects authorization — that's a local `client_ref` | `X-Internal-Token` | — |
| `admin-api` → `platform-api` (admin surface) | `/api/platform/admin/*` | 5s | `503 "Platform Core unavailable"` (not survivable — `admin-api` has no data of its own) | Forwarded user bearer | Byte-for-byte pre-split contract preserved |
| `admin-api` → `talent-api` (enrichment) | `/api/talent/summary`, internal client-name lookups | 5s | Degrades gracefully — names fall back to raw ids, pending count shows `0` | `X-Internal-Token` | — |

## 7. Closed

This document reflects Waves A–F of the Architecture Completion Plan and is
**closed** unless a material business requirement, security problem,
verified defect, or architectural violation genuinely requires a change —
see `CLAUDE.md`'s "DIJIONE PLATFORM DATA OWNERSHIP AND SOURCE
SYNCHRONIZATION CONTRACT" for the same closure rule at the contract level.
