# People / Workforce Source (BambooHR) — DijiOne standard source-sync

**Status:** an independently deployable service, `apps/people-api` (port
8006, `people_dev`) — extracted from `birthday-api` in Architecture
Completion Plan Wave E. `birthday-api` consumes it exclusively over HTTP
via `EmployeeDirectoryClient`; it holds no BambooHR credential and imports
nothing from `app.integrations.bamboohr`
(`apps/birthday-api/tests/test_no_direct_bamboohr_dependency.py` guards
this). Follows the same **DijiOne standard source-synchronization
lifecycle** as `recruitment-api` — see `docs/platform/recruitment-source.md`
and the authoritative rules in `CLAUDE.md`'s "DIJIONE PLATFORM DATA
OWNERSHIP AND SOURCE SYNCHRONIZATION CONTRACT".

## What it owns

- The BambooHR client + adapter (`app/integrations/bamboohr/*`), the
  employee-shaping mapper, and the durable read model: `employees` (keyed
  on `bamboohr_id`), `people_sync_runs`.
- `GET /api/people/employees/{bamboohr_id}?include_inactive_live_lookup=true`
  is a deliberate escape hatch for historical/terminated employees not in
  the active-employee sync scope: a single live BambooHR GET, never
  persisted into the `employees` table. `EmployeeDirectoryClient.get_employee()`
  always passes this flag.

**Not owned here:** `BirthdayOrder` and its employee snapshot columns
(operational, order-time facts — `docs/platform/data-ownership.md` §5),
suppliers, delivery workflow, any birthday-domain business logic.

## Sync lifecycle

Same shape as Recruitment Source, tuned to People's own approved cadence
(daily, not 6-hourly — birthday detection is date-bound, not stream-like):

| Concern | Implementation |
|---|---|
| **Scheduled reconciliation** | Daily, via the `people-sync-job` Container Apps Job → `POST /api/people/internal/scheduled-sync` (`X-Internal-Token`). Not an in-process timer. `birthday-scan-job` runs 30 min later. |
| **Ad-hoc sync** | `POST /api/people/internal/sync` (202, single-flight). |
| **Async** | 202 + `run_id`; the run executes in the background. |
| **Idempotent** | Insert new / update changed / keep stable ids on `bamboohr_id`; a failed run leaves the previous employee read model intact. |
| **Freshness** | `GET /api/people/freshness` → `last_successful_sync_at` + latest-run summary. |
| **Notifications** | Same silent-success / operational-warning-on-failure pattern via `PlatformClient`, best-effort. |

## Failure isolation — "defer and self-heal", not a local mirror

`people-api` down does **not** get a fail-closed local projection the way
`recruitment-api` does for `talent-api` — birthday detection is a
**workflow trigger**, not an authorization decision, so the correct and
architecturally required response is to defer, not to mirror employee data
into `birthday_dev`. The full contract — `ScanRunStatus.DEFERRED_SOURCE_UNAVAILABLE`,
the forward-occurrence-window self-heal, and why in-flight `BirthdayOrder`
rows are completely unaffected — is documented once, in
`docs/platform/data-ownership.md` §4b, rather than duplicated here.

## Mock mode

`INTEGRATIONS_MODE=mock` (default) drives the whole lifecycle against
`MockBambooHRClient` — CI, local dev, and the first shared DEV run
end-to-end with **no BambooHR credentials**. No live BambooHR call has been
made against this codebase to date (unlike Lever, which had a one-time
GET-only live verification — see `docs/platform/recruitment-source.md`).
