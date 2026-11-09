# DijiAtWork — module foundation (Stage B1)

**Status:** foundation plus the employee attendance engine. Employee linking and
Management functions are not built.

| Component | Location | Local |
|---|---|---|
| Backend | `apps/atwork-api` | FastAPI, port 8009, `/api/atwork` |
| Frontend | `apps/atwork-web` | Next.js zone, port 3005, base path `/atwork` |

## Backend routes

| Route | Access | Purpose |
|---|---|---|
| `GET /health`, `GET /health/deep` | Public | Liveness and readiness |
| `GET /api/atwork/metadata` | Public | Module identity |
| `GET /api/atwork/summary` | Public | DijiOne Home status card |
| `GET /api/atwork/me` | Bearer token | Caller identity, role and permissions from verified claims |
| `GET /api/atwork/management/access` | `atwork.management.access` | Access check for the future Management area |
| `GET /api/atwork/attendance/{status,today,history,sessions/{id}}` | `atwork.attendance.read_own` | The caller's own attendance |
| `POST /api/atwork/attendance/{check-in,breaks/start,breaks/end,check-out}` | `atwork.attendance.record_own` | Record the caller's own attendance |

A valid token without a DijiAtWork role receives `module_access: false` and no
permissions. Outside development, the service refuses to start with the default
secrets.

## Frontend pages

`/` (landing) plus placeholders at `/today`, `/history` and `/management`. The
Management area is shown only with `atwork.management.access`, which `atwork-api`
also enforces.

## Known limitations of the attendance engine (Stage C1)

- **PostgreSQL testing.** Migrations and concurrency are tested on SQLite only.
  The PostgreSQL DDL was generated offline but never executed, and the CI
  migration job for `atwork-api` has not run yet. Row locking
  (`with_for_update`) has no effect on SQLite, so concurrent behaviour must be
  verified on PostgreSQL before hosted use.
- **Audit immutability.** `attendance_events` is append-only at the ORM level:
  listeners reject updates and deletes made through ORM objects. Bulk or raw SQL
  and direct database access are not blocked. Database-level protection, such as
  restricted grants or a trigger, is a later decision.
- **Non-overlap.** The database enforces one open session and one open break.
  Overlap between completed records is prevented only by the service's ordering
  checks, so any later correction flow must validate it as well.
- **Employee identity linking.** Records key on `platform_user_id` from verified
  claims. There is no link to the Workforce Directory, so a deactivated employee
  is limited only by platform access and token expiry (up to 12 hours).

## Platform registration

The module is registered as `COMING_SOON`. See `administration.md` for the
central and local responsibilities and `module-removal.md` for the removal gate.
