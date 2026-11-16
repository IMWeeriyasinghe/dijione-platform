# View as User (V1)

A **Super Admin** can open a **read-only** session that shows DijiOne exactly as a chosen **internal
employee** sees it: the same applications, roles, permissions and client scope. Nothing done in the
session can change data. It exists to explain and verify access ("why can't Tara see this?"), not to act
for someone.

## Who, and as whom

| | Rule |
|---|---|
| Administrator | Platform role `SUPER_ADMIN` **and** permission `platform.admin.view_as` (held by `SUPER_ADMIN` only; `PLATFORM_ADMIN` does not get it). Both are checked by `platform-api` on every start. |
| Employee | An **active internal employee** (`internal_employee`, set only by a verified Microsoft sign-in), not the administrator. One answer is given for every refusal, so the endpoint does not reveal who exists. |
| Out of V1 | Supplier-portal users, external-link (magic-link) users, and role simulation ("what would a TA Member see?"). Supplier and external sessions are other actor populations and are never targets. |

## What starts and ends a session

* **Start** — Admin Center → Users → a person → **View as**. The dialog lists the person's applications, role,
  number of permissions and client scope, then **Start read-only session**. `POST /api/admin/view-as`
  (admin-api, pass-through) → `POST /api/platform/admin/view-as`.
* The tab goes to the DijiOne home page as that employee. A **banner on every page of every application**
  names the employee, says it is read-only and recorded, shows when it ends, and has **Exit View as**.
* **End** — Exit View as (or Sign out in that tab, which means the same), expiry (30 minutes,
  `VIEW_AS_MINUTES`), starting another session (replaces the previous one), the administrator being
  deactivated, demoted or having their own access changed, or **any change to the employee's access or
  status**. The administrator is returned to the page they started from; their own session was never touched.

There is **no refresh**: when a session ends, the administrator starts a new one.

## The token

The token is signed for the **employee** (`sub` and every authorization claim are theirs), so each
application authorizes a request exactly as it would the employee. It carries `actor_type = view_as` and a
`view_as` claim (`session_id`, `actor_id`, `actor_name`, `actor_av`), and no `sst`.

* `platform-api` accepts only `actor_type = staff` as a user session, so a View-as token is refused with
  **403 `view_as_read_only`** by every staff-only endpoint, including `/api/auth/refresh`. It cannot be
  refreshed or exchanged for a normal session.
* Three read-only endpoints a shell needs to draw itself accept it, answering for the employee:
  `GET /api/auth/me` (which also returns the banner facts), `GET /api/modules`, `GET /api/notifications`.
  They check the session against the database on every call, so ending it is immediate there.
* In the browser it lives in **this tab's `sessionStorage`**, beside the administrator's untouched staff
  session in `localStorage`. While it exists every request in the tab carries it. A failure of the View-as
  session (a 401) ends only that session.

## Enforcement: read-only for every application

Implemented once in `packages/auth-client-py` and used by every API that verifies user tokens
(talent, birthday, onsite, atwork, spark). Three independent layers:

1. **Route gate.** A View-as request is admitted only to a `GET` route that the service's route policy
   (`app/core/revocation_policy.py`) marks `READ`. Changes, own-data actions (`OWN`), sensitive reads and
   exports (`SENSITIVE`), unlisted routes, and every route of a service with no registered policy are
   refused with 403. This runs whatever the revocation setting, and a token that says `view_as` without
   its detail claim is still read-only. The HTTP method is never trusted alone: a `GET` that writes is not
   `READ` (a test per service enforces this).
2. **Database backstop.** An admitted request sets a context flag. A SQLAlchemy listener then refuses any
   flush, `INSERT`/`UPDATE`/`DELETE` or DDL in that request, even from a `READ` handler that writes by
   mistake.
3. **No side effects.** `PlatformClient` sends no audit events or notifications while the flag is set, so a
   `READ` route cannot cause a notification, background job or approval.

Because the policy tables already keep bulk personal data, exports, approvals, syncs and administration out
of `READ`, a View-as session cannot export, approve, send, sync, or open an admin action.

## Audit

Recorded in the platform audit log with the **employee as the subject**, so it appears in their history
(Users → person → Audit History / Diagnostics):

| Action | When |
|---|---|
| `view_as.started` | a session begins (administrator, employee, session id, expiry) |
| `view_as.ended` | the administrator ends it (once, however many times they click) |
| `view_as.blocked` | any application refuses a View-as request (method and path), recorded off the request path |

Sessions are also rows in `view_as_sessions`.

## Operations

* **Migration** `i5k7m9n1p3q4` (after `h4j6k8m0n2p3`): creates `view_as_sessions`, registers
  `platform.admin.view_as` and links it to `SUPER_ADMIN` only, raises every `access_version`. Additive;
  downgrade drops only the table. The permission becomes usable once a Super Admin's session is re-issued.
* **Feature flag `VIEW_AS_ENABLED`** (platform-api, **default off**). While it is off, starting a session
  returns 404 "View as is not enabled in this environment" and nothing else changes. Turn it on one
  environment at a time. This is also the kill switch: set it back to `false` and no new session can start
  (an existing one ends within 30 minutes, or immediately if the administrator ends it).
* **Enforcement does not depend on the flag.** An application API refuses changes from any View-as token it
  is shown, whether or not the flag is on.
* **Settings:** `VIEW_AS_MINUTES` (platform-api, default 30). Applications need nothing new.
* **Order:** platform-api (migration, then code) → application APIs (library with the enforcement) →
  web apps (banner and session handling) → admin-web (the action) → only then `VIEW_AS_ENABLED=true`. An
  application API that has not yet taken the new library ignores the token's `view_as` claim *and would
  authorize the employee's token for changes*, so **never set `VIEW_AS_ENABLED=true` in an environment
  until every user-token API there (talent, birthday, onsite, atwork, spark) runs the new library.**
* **Rollback:** set `VIEW_AS_ENABLED=false`; or redeploy the previous images. The table and permission stay
  in place (harmless).

## Known limits (V1)

* A View-as session shows data as the employee's access allows it, including personal data they can read.
  That is the purpose; it is why only Super Admins can start one and why it is audited.
* Revocation of an already-issued View-as token in an application API depends on the application having
  `REVOCATION_ENABLED`; otherwise it is bounded by the 30-minute lifetime. `platform-api` endpoints check
  the session on every call regardless.
* Exports and downloads are refused rather than simulated.

## Tests

`platform-api`: `tests/test_view_as.py`, `tests/test_view_as_migration.py`. Shared enforcement:
`packages/auth-client-py/tests/test_view_as.py`. Every route of every affected API:
`apps/*/tests/test_revocation_wiring.py`. Client: `apps/shell-web/src/__tests__/view-as.test.tsx`.
Admin UI: `apps/admin-web/src/app/__tests__/view-as.test.tsx`.
