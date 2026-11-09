# DijiAtWork — V1 application

**Status:** V1 employee and Management functionality, tested locally. The module
remains `COMING_SOON`, and no hosted environment has been configured for it.
DijiAtWork records operational working hours. It is not payroll.

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
| `GET /api/atwork/management/access` | `atwork.management.access` | Management access check |
| `GET /api/atwork/attendance/{policy,status,today,history,sessions/{id}}` | `atwork.attendance.read_own` | The caller's own attendance |
| `POST /api/atwork/attendance/{check-in,breaks/start,breaks/end,check-out}` | `atwork.attendance.record_own` | Record the caller's own attendance |
| `GET, POST /api/atwork/corrections`, `GET /{id}`, `POST /{id}/withdraw` | `atwork.corrections.request_own` | The caller's own correction requests |
| `GET /api/atwork/management/{overview,employees,employees/{id}/attendance,sessions/{id}}` | Management + `atwork.attendance.read` | Organization-wide attendance |
| `GET /api/atwork/management/corrections`, `GET /{id}` | Management + `atwork.corrections.review` | Queue, history, original and proposed values |
| `POST /api/atwork/management/corrections/{id}/{approve,reject}` | Management + `atwork.corrections.approve` | Decide another employee's request |
| `GET /api/atwork/management/reports/{summary,missed-checkouts,corrections}` | Management + `atwork.reports.read` | Reports |
| `GET /api/atwork/management/reports/export` | Management + `atwork.reports.read` + `atwork.reports.export` | CSV and Excel |
| `GET, PUT /api/atwork/management/settings` | Management + `atwork.settings.manage` | Local policy |
| `GET /api/atwork/management/audit` | Management + `atwork.audit.read` | Audit history |
| `POST /api/atwork/internal/notifications/run` | Internal service secret | Scheduled alerts and notification delivery |

A valid token without a DijiAtWork role receives `module_access: false` and no
permissions. Outside development, the service refuses to start with the default
secrets.

## Frontend pages

Employee: `/` (Today), `/attendance`, `/attendance/[sessionId]`, `/requests`,
`/requests/new`. Management: `/management`, `/management/employees`,
`/management/employees/[userId]`, `/management/sessions/[id]`,
`/management/corrections`, `/management/corrections/[id]`, `/management/reports`,
`/management/audit`, `/management/settings`. All sit under `/atwork`.
Navigation follows permissions; `atwork-api` enforces them.

## Decisions made for V1

- `corrections.review` allows viewing. `corrections.approve` allows approving
  and rejecting. Nobody may decide their own request.
- An approved correction updates the session. The request keeps the original
  values, audit events keep before and after, and replaced breaks stay in the
  table as voided rows.
- A request goes stale if its session changes before the decision. It must then
  be rejected and submitted again, so an approval cannot overwrite newer data.
- `attendance_employees` holds a name and email snapshot from verified claims,
  taken at check-in or correction request. Employee search covers only people who
  have done one of those. It is not an identity or role record.
- The missed check-out threshold defaults to 12 hours. Sessions are flagged only.
- Downgrading migration `0002_atwork_corrections` is refused while correction or
  voided-break history exists.

## Check-out and corrections

- Check Out always asks for confirmation. There is no Undo: a completed session
  changes only through an approved correction.
- Checking in again starts a new session. Sessions on the same day add up.
  Time between them counts only if a missing-session request is approved.

## Notifications

In-app only, through Platform Core. Each is written to `notification_outbox` in
the same transaction as the attendance change, then delivered after the response
and retried every 15 minutes by `atwork-notifications-job` (backoff, 12 attempts).
Platform Core's per-recipient key makes a retry invisible to the user. Reviewers
are resolved by effective permission (`atwork.management.access` and
`atwork.corrections.review`), never by role name, and requesters are excluded
from notices about their own request. Text contains no times or employee names.

| Event | Recipient | Once per |
|---|---|---|
| Correction requested or withdrawn | Reviewers | Request |
| Correction approved or rejected (with reason) | Employee | Request |
| Missed check-out threshold passed | Employee | Session |
| Requests pending over 24 hours | Reviewers (one digest, from 09:00 business time) | Business day |

## Exports

Names follow `DijiAtWork_<Report>_Report_YYYY-MM-DD_HHmmss.<ext>` in the business
time zone. Excel has real date cells and an Export Information sheet. CSV uses
ISO 8601 with offsets, and every row ends with the report name, period, generation
time and time zone. A report with no rows has a header only.

## Local browser test

```
export PLATFORM_API_URL=http://127.0.0.1:18000 ATWORK_API_URL=http://127.0.0.1:18009 ATWORK_WEB_URL=http://127.0.0.1:13005
npm run build -w atwork-web && npm run build -w shell-web
node apps/atwork-web/e2e/run.mjs
```

The test runs through the DijiOne shell. It uses disposable SQLite databases and the seeded development personas.

## Known limitations

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
  checks, and correction approval re-checks it.
- **Report scale.** Reports and exports are computed in memory, limited by the
  366-day range. Measure them with production volumes before relying on them.
- **Employee identity linking.** Records key on `platform_user_id` from verified
  claims. There is no link to the Workforce Directory, so a deactivated employee
  is limited only by platform access and token expiry (up to 12 hours).

- **Email.** Notifications are in-app only. Email needs an approved sender, an
  Exchange RBAC mailbox scope and `atwork-api`'s own managed identity
  (`docs/platform/email-architecture.md`).

## Platform registration

The module is registered as `COMING_SOON`. See `administration.md` for the
central and local responsibilities and `module-removal.md` for the removal gate.
